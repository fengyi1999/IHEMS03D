"""
Simulink接收器 - 负责接收来自Simulink的TCP数据或生成模拟数据
"""
import time
import asyncio
import threading
import struct
import socket
import random
import numpy as np
from datetime import datetime
import config
from queue import Queue
import json
import subprocess

# 全局消息队列，用于存储TCP数据，供WebSocket读取
data_queue = Queue()

class SimulinkReceiver:
    """
    处理与Simulink模型的通信或生成模拟数据
    使用异步I/O和消息队列实现非阻塞通信
    """
    def __init__(self, data_callback=None, test=False): # 添加 test 参数
        """
        初始化SimulinkReceiver

        参数:
            data_callback: 接收到数据后的回调函数
            test: 是否启用测试模式
        """
        self.data_callback = data_callback
        self.test = test # 存储测试模式标志
        self.running = False
        self.server_socket = None
        self.client_socket = None
        self.simulator_thread = None
        self.data_queue = data_queue  # 使用全局队列
        self.loop_thread = None
        self.loop = None
        self.data_buffer_for_aggregation = []
        # 从配置中获取聚合分钟数，默认为1（不聚合）
        self.aggregation_minutes = getattr(config, 'AGGREGATION_MINUTES', 1)
        if self.aggregation_minutes > 1:
            print(f"数据聚合模式已启用: 将每 {self.aggregation_minutes} 个1分钟数据点聚合为一个数据点。")

    def start_tcp_server(self):
        """
        启动TCP服务器，用于接收Simulink数据
        使用异步I/O实现非阻塞监听
        """
        try:
            # 创建事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.loop = loop # 保存loop的引用

            # 启动TCP服务器的异步任务
            server_task = loop.create_task(self._async_tcp_server())

            # 在新线程中运行事件循环
            def run_event_loop():
                try:
                    loop.run_forever()
                except Exception as e:
                    print(f"事件循环出错: {e}")
                finally:
                    loop.close()

            # 启动事件循环线程
            self.loop_thread = threading.Thread(target=run_event_loop)
            self.loop_thread.daemon = True
            self.loop_thread.start()

            print(f"TCP服务器已启动，监听地址: {config.TCP_HOST}:{config.TCP_PORT}")
            print(f"等待SimSend.py连接到端口 {config.TCP_PORT}...")
            print("智慧绿氢管理系统已启动")
            self.running = True

            return True
        except Exception as e:
            import traceback
            print(f"启动TCP服务器失败: {e}")
            print(traceback.format_exc())
            return False

    async def _async_tcp_server(self):
        """
        异步TCP服务器实现
        """
        try:
            # 首先检查端口是否被占用
            try:
                result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True, shell=True)
                if f":{config.TCP_PORT}" in result.stdout:
                    print(f"警告: 端口 {config.TCP_PORT} 已被占用")
                    # 尝试查找占用进程
                    lines = result.stdout.split('\n')
                    for line in lines:
                        if f":{config.TCP_PORT}" in line and "LISTENING" in line:
                            parts = line.split()
                            if len(parts) >= 5:
                                pid = parts[-1]
                                print(f"端口被进程 PID {pid} 占用")
                                # 尝试查找进程名
                                try:
                                    proc_result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], 
                                                                capture_output=True, text=True, shell=True)
                                    if proc_result.returncode == 0:
                                        print(f"进程信息: {proc_result.stdout}")
                                except:
                                    pass
                            break
            except Exception as e:
                print(f"检查端口占用时出错: {e}")

            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # 设置SO_REUSEADDR选项
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((config.TCP_HOST, config.TCP_PORT))
            self.server_socket.listen(1)
            self.server_socket.setblocking(False)

            while self.running:
                try:
                    client_socket, addr = await asyncio.get_event_loop().sock_accept(self.server_socket)
                    print(f"接受来自 {addr} 的连接")
                    self.client_socket = client_socket
                    # 将_handle_client作为任务调度，确保它在事件循环中运行
                    asyncio.create_task(self._handle_client(client_socket))
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"处理客户端连接时出错: {e}")
                    if self.client_socket:
                        self.client_socket.close()
                        self.client_socket = None
        except Exception as bind_error:
            print(f"TCP服务器绑定端口失败: {bind_error}")
            if "10013" in str(bind_error):
                print("这通常是因为:")
                print("1. 端口已被其他程序占用（如MySQL、其他服务）")
                print("2. 权限不足（尝试以管理员身份运行）")
                print("3. Windows防火墙阻止")
                print(f"建议: 修改config.py中的TCP_PORT为其他端口号，或停止占用端口{config.TCP_PORT}的服务")
            raise bind_error
        finally:
            if self.server_socket:
                self.server_socket.close()
                self.server_socket = None

    async def _handle_client(self, client_socket):
        """
        处理客户端连接
        异步读取TCP数据并将其放入队列

        参数:
            client_socket: 客户端socket
        """
        addr = client_socket.getpeername() # 直接从client_socket获取地址

        # 数据缓冲区
        data_buffer = b''
        data_count = 0

        # 数据格式参数（与SimSend3.py一致）
        single_values_count = 9
        matrix_count = 5
        matrix_size = 20
        bytes_per_double = 8
        bytes_per_point = (single_values_count + matrix_count * matrix_size) * bytes_per_double

        try:
            while self.running:
                # 异步读取数据
                # 直接使用sock_recv，避免open_connection可能带来的事件循环问题
                data = await asyncio.get_event_loop().sock_recv(client_socket, 4096)

                if not data:  # 如果没有数据，表示连接已关闭
                    break

                # 将新数据添加到缓冲区
                data_buffer += data

                # 处理完整的数据包
                while len(data_buffer) >= bytes_per_point:
                    # 提取一个完整的数据点
                    point_data = data_buffer[:bytes_per_point]
                    data_buffer = data_buffer[bytes_per_point:]

                    # 解析数据
                    parsed_data = self._parse_data(point_data, single_values_count, matrix_count, matrix_size)

                    # 将数据放入队列
                    if parsed_data:
                        if self.aggregation_minutes > 1:
                            self.data_buffer_for_aggregation.append(parsed_data)
                            # 检查缓冲区是否已满
                            if len(self.data_buffer_for_aggregation) >= self.aggregation_minutes:
                                aggregated_data = self._aggregate_data(self.data_buffer_for_aggregation)
                                self.data_queue.put(aggregated_data)
                                if self.data_callback:
                                    self.data_callback(aggregated_data)
                                # 清空缓冲区
                                self.data_buffer_for_aggregation = []
                        else:
                            # 不进行聚合，直接将数据放入队列
                            self.data_queue.put(parsed_data)
                            if self.data_callback:
                                self.data_callback(parsed_data)

                        data_count += 1
                        # 计数器增加，不需要每10个输出一次
        except asyncio.CancelledError:
            # 处理取消异常
            pass
        except Exception as e:
            import traceback
            print(f"处理TCP客户端数据时出错: {e}")
            print(traceback.print_exc())
        finally:
            # 关闭连接
            try:
                client_socket.shutdown(socket.SHUT_RDWR)
                client_socket.close()
            except Exception as e:
                print(f"关闭客户端socket时出错: {e}")
            # 只在非speed模式或test模式下输出连接信息
            if config.SPEED <= 1 or self.test:
                print(f"TCP客户端连接已关闭: {addr}")
                print("等待新连接...")

    def _aggregate_data(self, data_points):
        """
        将数据点列表聚合为单个数据点。
        """
        if not data_points:
            return None

        # 使用最后一个数据点作为聚合数据的模板
        aggregated_data = data_points[-1].copy()
        aggregated_data['data'] = data_points[-1]['data'].copy()

        # 获取所有'data'字典
        all_data_dicts = [dp['data'] for dp in data_points]
        num_points = len(all_data_dicts)

        # 需要平均的字段
        fields_to_average = [
            'wind_power', 'solar_power', 'fess_power', 'bess_power', 'grid_power',
            'hydrogen_total_power', 'hydrogen_load', 'hydrogen_soc', 'hydrogen_hss',
            'grid_voltage', 'grid_frequency', 'wind_power_forecast', 'solar_power_forecast',
            'storage_power', 'hydrogen_set_power', 'hydrogen_real_power',
        ]

        # 需要平均的矩阵字段
        matrix_fields_to_average = [
            'electrolyzer_set_power', 'hydrogen_rate', 'electrolyzer_real_power', 'electrolyzer_temp'
        ]

        # 需要求和的字段
        fields_to_sum = [
            'hydrogen_production'
        ]

        aggregated_values = {}

        # 平均单值字段
        for field in fields_to_average:
            if field in all_data_dicts[0]:
                values = [d.get(field, 0) for d in all_data_dicts]
                aggregated_values[field] = sum(values) / num_points

        # 平均矩阵字段
        for field in matrix_fields_to_average:
            if field in all_data_dicts[0] and isinstance(all_data_dicts[0][field], list):
                # 转置并平均
                transposed = list(zip(*[d.get(field, [0]*20) for d in all_data_dicts]))
                aggregated_values[field] = [sum(vals)/len(vals) for vals in transposed]

        # 求和字段
        for field in fields_to_sum:
            if field in all_data_dicts[0]:
                values = [d.get(field, 0) for d in all_data_dicts]
                aggregated_values[field] = sum(values)

        # 更新聚合数据字典
        aggregated_data['data'].update(aggregated_values)
        
        # 添加聚合信息，以便前端可以显示
        aggregated_data['aggregation_info'] = {
            'minutes': self.aggregation_minutes,
            'count': num_points
        }

        if self.test or self.aggregation_minutes > 1:
             print(f"已聚合 {num_points} 个数据点为 1 个 {self.aggregation_minutes} 分钟数据点。")

        return aggregated_data

    def _parse_data(self, data, single_values_count, matrix_count, matrix_size):
        """
        解析从服务器接收的二进制数据

        参数:
            data: 二进制数据
            single_values_count: 单个值的数量
            matrix_count: 矩阵数量
            matrix_size: 每个矩阵的大小

        返回:
            解析后的数据字典
        """
        try:
            # 获取当前时间戳(乘以speed参数)
            # 在speed模式下，时间戳应该按照真实时间流逝，但数据接收频率会增加
            timestamp = int(time.time())

            # 解析单值数据
            format_str = '<' + 'd' * single_values_count
            single_values = struct.unpack(format_str, data[:single_values_count * 8])

            # 解析矩阵数据
            matrices = []
            offset = single_values_count * 8
            for _ in range(matrix_count):
                matrix_format = '<' + 'd' * matrix_size
                matrix_data = struct.unpack(matrix_format,
                                           data[offset:offset + matrix_size * 8])
                matrices.append(matrix_data)
                offset += matrix_size * 8

            # 创建数据对象
            # 将数据映射到app.py中使用的变量名
            # 将功率数据除以1000，从kW转换为MW
            result = {
                'timestamp': timestamp,
                'data': {
                    'wind_power': single_values[0] / 1000,
                    'solar_power': single_values[1] / 1000,
                    'fess_power': single_values[2] / 1000,
                    'bess_power': single_values[3] / 1000,
                    'grid_power': single_values[4] / 1000,
                    'hydrogen_total_power': single_values[5] / 1000,
                    'hydrogen_load': single_values[6],
                    'hydrogen_soc': single_values[7],
                    'hydrogen_hss': single_values[8],

                    # 添加其他单值数据
                    'grid_connected_status': 1,  # 电网连接状态
                    'storage_running_status': 1,  # 储能运行状态
                    'system_enable_status': 1,  # 系统启用状态
                    'hydrogen_running_status': 1,  # 制氢系统运行状态
                    'grid_export_power': max(0, -single_values[0]) / 1000,  # 电网输出功率
                    'grid_import_power': max(0, single_values[0]) / 1000,  # 电网输入功率

                    # 计算其他变量的模拟值
                    'grid_voltage': 10.0 + random.uniform(-0.05, 0.06),  # 电网电压
                    'grid_frequency': 50.0 + random.uniform(-0.2, 0.2),  # 电网频率
                    'wind_power_forecast': (single_values[4] / 1000) * (1 + random.uniform(-0.1, 0.2)),  # 风电预测
                    'solar_power_forecast': (single_values[3] / 1000) * (1 + random.uniform(-0.1, 0.2)),  # 光伏预测
                    'storage_power': (single_values[2] + single_values[3]) / 1000,  # 储能总功率
                    # 使用app.py中计算的风电利用率和光伏利用率替代renewable_utilization
                    'hydrogen_set_power': sum(matrices[1]) / len(matrices[1]) / 1000,  # 制氢设定功率
                    'hydrogen_real_power': sum(matrices[3]) / len(matrices[3]) / 1000,  # 制氢实际功率
                    'hydrogen_production': sum(matrices[2]),  # 产氢量
                    # 使用app.py中计算的绿电比率替代green_energy_ratio
                    'system_runtime': random.randint(1000, 10000),  # 系统运行时间

                    # 添加电解槽矩阵数据
                    'electrolyzer_status': list(matrices[0]),
                    'electrolyzer_set_power': [power / 1000 for power in matrices[1]],  # 除以1000转换为MW
                    'hydrogen_rate': list(matrices[2]),
                    'electrolyzer_real_power': [power / 1000 for power in matrices[3]],  # 除以1000转换为MW
                    'electrolyzer_temp': list(matrices[4])
                }
            }

            # 仅在测试模式下输出调试信息
            if self.test == 1:
                print("电解槽实际功率数据:", result['data']['electrolyzer_real_power'])
            return result
        except Exception as e:
            import traceback
            print(f"解析数据时出错: {e}")
            print(traceback.format_exc())
            return None

    def start_simulator(self):
        """
        启动模拟数据生成器
        """
        if config.SIMULATE_DATA:
            self.running = True
            self.simulator_thread = threading.Thread(target=self._generate_simulated_data)
            self.simulator_thread.daemon = True
            self.simulator_thread.start()
            print(f"模拟数据生成器已启动，间隔: {config.SIMULATE_INTERVAL}秒")
            return True
        else:
            # 即使不是模拟模式，也启动一个简单的模拟数据生成器，以便在没有TCP连接时也能显示一些数据
            print("注意: 虽然未启用模拟数据模式，但将启动一个临时模拟数据生成器，直到TCP连接建立")
            self.running = True
            self.simulator_thread = threading.Thread(target=self._generate_temp_simulated_data)
            self.simulator_thread.daemon = True
            self.simulator_thread.start()
            return True

    def _generate_temp_simulated_data(self):
        """
        生成临时模拟数据，用于在TCP连接建立前显示一些数据
        """
        print("启动临时模拟数据生成器")

        # 初始化电解槽状态和功率
        electrolyzer_status = [0] * 20
        electrolyzer_set_power = [0] * 20
        electrolyzer_real_power = [0] * 20
        hydrogen_rate = [0] * 20
        electrolyzer_temp = [0] * 20

        # 根据新的状态值定义：
        # 状态值 0 表示检修
        # 状态值 1 表示冷备待机
        # 状态值 2 3 4 均表示冷启动
        # 状态值 5 表示热备
        # 状态值 6 表示热启动
        # 状态值 7 表示运行

        # 设置一些电解槽为运行状态
        for i in range(5):
            electrolyzer_status[i] = 7  # 运行状态
            electrolyzer_set_power[i] = 3.0  # 3MW
            electrolyzer_real_power[i] = 2.8  # 2.8MW
            hydrogen_rate[i] = 500  # 500 Nm³/h
            electrolyzer_temp[i] = 70  # 70°C

        # 设置一些电解槽为冷备待机状态
        for i in range(5, 8):
            electrolyzer_status[i] = 1  # 冷备待机状态
            electrolyzer_set_power[i] = 0
            electrolyzer_real_power[i] = 0
            hydrogen_rate[i] = 0
            electrolyzer_temp[i] = 30  # 30°C

        # 设置一些电解槽为冷启动状态
        for i in range(8, 11):
            electrolyzer_status[i] = 2  # 冷启动状态(2,3,4均表示冷启动)
            electrolyzer_set_power[i] = 1.0
            electrolyzer_real_power[i] = 0.8
            hydrogen_rate[i] = 150
            electrolyzer_temp[i] = 45  # 45°C

        # 设置一些电解槽为热备状态
        for i in range(11, 13):
            electrolyzer_status[i] = 5  # 热备状态
            electrolyzer_set_power[i] = 0.5
            electrolyzer_real_power[i] = 0.3
            hydrogen_rate[i] = 50
            electrolyzer_temp[i] = 60  # 60°C

        # 设置一些电解槽为热启动状态
        for i in range(13, 15):
            electrolyzer_status[i] = 6  # 热启动状态
            electrolyzer_set_power[i] = 1.5
            electrolyzer_real_power[i] = 1.2
            hydrogen_rate[i] = 200
            electrolyzer_temp[i] = 65  # 65°C

        # 设置一些电解槽为检修状态
        for i in range(15, 20):
            electrolyzer_status[i] = 0  # 检修状态
            electrolyzer_set_power[i] = 0
            electrolyzer_real_power[i] = 0
            hydrogen_rate[i] = 0
            electrolyzer_temp[i] = 25  # 25°C

        counter = 0
        while self.running:
            try:
                # 获取当前时间戳(在speed模式下保持真实时间)
                timestamp = int(time.time())

                # 生成一些波动
                for i in range(20):
                    # 根据新的状态值定义：
                    # 状态值 0 表示检修
                    # 状态值 1 表示冷备待机
                    # 状态值 2 3 4 均表示冷启动
                    # 状态值 5 表示热备
                    # 状态值 6 表示热启动
                    # 状态值 7 表示运行

                    if electrolyzer_status[i] == 7:  # 运行状态
                        # 添加一些随机波动
                        electrolyzer_real_power[i] = 2.8 + random.uniform(-0.2, 0.2)
                        hydrogen_rate[i] = 500 + random.uniform(-20, 20)
                        electrolyzer_temp[i] = 70 + random.uniform(-2, 2)
                    elif electrolyzer_status[i] in [2, 3, 4]:  # 冷启动状态
                        electrolyzer_real_power[i] = 0.8 + random.uniform(-0.1, 0.1)
                        hydrogen_rate[i] = 150 + random.uniform(-10, 10)
                        electrolyzer_temp[i] = 45 + random.uniform(-1, 1)
                    elif electrolyzer_status[i] == 5:  # 热备状态
                        electrolyzer_real_power[i] = 0.3 + random.uniform(-0.05, 0.05)
                        hydrogen_rate[i] = 50 + random.uniform(-5, 5)
                        electrolyzer_temp[i] = 60 + random.uniform(-1, 1)
                    elif electrolyzer_status[i] == 6:  # 热启动状态
                        electrolyzer_real_power[i] = 1.2 + random.uniform(-0.1, 0.1)
                        hydrogen_rate[i] = 200 + random.uniform(-10, 10)
                        electrolyzer_temp[i] = 65 + random.uniform(-1, 1)

                # 创建模拟数据
                data = {
                    'timestamp': timestamp,
                    'data': {
                        # 单值数据
                        'wind_power': 15.0 + random.uniform(-1, 1),  # 风电实时出力 (MW)
                        'solar_power': 10.0 + random.uniform(-0.5, 0.5),  # 光伏实时出力 (MW)
                        'grid_storage': 5.0 + random.uniform(-0.3, 0.3),  # 构网储能实时出力 (MW)
                        'follow_storage': 3.0 + random.uniform(-0.2, 0.2),  # 跟网储能实时出力 (MW)
                        'grid_power': -8.0 + random.uniform(-1, 1),  # 电网实时功率 (MW)，负值表示上网
                        'hydrogen_total_power': 14.0 + random.uniform(-0.5, 0.5),  # 制氢总功率 (MW)

                        # 矩阵数据
                        'electrolyzer_status': electrolyzer_status.copy(),
                        'electrolyzer_set_power': electrolyzer_set_power.copy(),
                        'hydrogen_rate': hydrogen_rate.copy(),
                        'electrolyzer_real_power': electrolyzer_real_power.copy(),
                        'electrolyzer_temp': electrolyzer_temp.copy(),

                        # 其他必要数据
                        'grid_connected_status': 1,
                        'storage_running_status': 1,
                        'system_enable_status': 1,
                        'hydrogen_running_status': 1,
                        'grid_voltage': 380.0 + random.uniform(-2, 2),
                        'grid_frequency': 50.0 + random.uniform(-0.1, 0.1),
                        'wind_power_forecast': 16.0 + random.uniform(-1, 1),
                        'solar_power_forecast': 11.0 + random.uniform(-0.5, 0.5),
                        'storage_power': 8.0 + random.uniform(-0.5, 0.5),
                        'hydrogen_set_power': 15.0 + random.uniform(-0.5, 0.5),
                        'hydrogen_real_power': 14.0 + random.uniform(-0.5, 0.5),
                        # 不生成renewable_utilization和green_energy_ratio，将由app.py中的计算结果替代
                        'system_runtime': counter * config.SIMULATE_INTERVAL
                    }
                }

                counter += 1

                # 每10秒输出一次调试信息 (仅在非speed模式或test模式下)
                if counter % 10 == 0 and (config.SPEED <= 1 or self.test):
                    print(f"临时模拟数据生成器已运行 {counter} 次")

                # 回调函数处理数据
                if self.data_callback:
                    self.data_callback(data)

                # 按照配置的间隔等待
                time.sleep(config.SIMULATE_INTERVAL)

            except Exception as e:
                print(f"生成临时模拟数据时出错: {e}")
                import traceback
                print(traceback.format_exc())
                time.sleep(1)

    def _generate_simulated_data(self):
        """
        生成模拟的Simulink数据
        """
        # 初始基础值
        base_values = {
            'power': 150.0,
            'voltage': 220.0,
            'current': 0.7,
            'frequency': 50.0,
            'active_power': 120.0,
            'reactive_power': 30.0,
            'power_factor': 0.95,
            'temperature': 25.0,
            'humidity': 50.0,
            'pressure': 101.3,
            'flow_rate': 1.5,
            'efficiency': 0.85,
            'soc': 75.0,
            'carbon_reduction': 15000.0,
            'energy_saved': 48000.0,
            'production': 156000.0,
            'consumption': 140000.0,
            'grid_load': 80.0,
            'battery_voltage': 48.0,
            'battery_current': 10.0
        }

        # 变化范围 (百分比)
        fluctuation_rates = {
            'power': 5,
            'voltage': 1,
            'current': 10,
            'frequency': 0.5,
            'active_power': 8,
            'reactive_power': 15,
            'power_factor': 2,
            'temperature': 3,
            'humidity': 5,
            'pressure': 1,
            'flow_rate': 10,
            'efficiency': 3,
            'soc': 2,
            'carbon_reduction': 0.1,
            'energy_saved': 0.1,
            'production': 2,
            'consumption': 3,
            'grid_load': 10,
            'battery_voltage': 2,
            'battery_current': 15
        }

        # 趋势变化参数
        trends = {var: 0 for var in config.VARIABLE_NAMES}

        while self.running:
            try:
                # 获取当前时间戳
                timestamp = int(time.time())

                # 生成模拟数据
                data = {'timestamp': timestamp, 'data': {}}

                for var in config.VARIABLE_NAMES:
                    # 更新趋势
                    if random.random() < 0.1:  # 10%概率改变趋势
                        trends[var] = random.uniform(-0.2, 0.2)

                    # 计算当前值
                    base = base_values[var]
                    fluctuation = base * (fluctuation_rates[var] / 100.0)
                    noise = random.uniform(-fluctuation, fluctuation)
                    trend_effect = base * trends[var]

                    # 确保值在合理范围内
                    current_value = max(0, base + noise + trend_effect)

                    # 更新基础值 (缓慢漂移)
                    base_values[var] = current_value

                    # 添加到数据集
                    data['data'][var] = round(current_value, 4)

                # 回调函数处理数据
                if self.data_callback:
                    self.data_callback(data)

                # 按照配置的间隔等待
                time.sleep(config.SIMULATE_INTERVAL)

            except Exception as e:
                print(f"生成模拟数据时出错: {e}")
                time.sleep(1)

    def stop(self):
        """停止服务"""
        self.running = False

        # 关闭客户端连接
        if self.client_socket:
            try:
                self.client_socket.shutdown(socket.SHUT_RDWR)
                self.client_socket.close()
            except:
                pass
            self.client_socket = None

        # 关闭服务器socket
        if self.server_socket:
            try:
                self.server_socket.shutdown(socket.SHUT_RDWR)
                self.server_socket.close()
            except:
                pass
            self.server_socket = None

        # 停止事件循环
        if self.loop and self.loop.is_running():
            self.loop.stop()

        if self.loop_thread and self.loop_thread.is_alive():
            self.loop_thread.join(timeout=5)

        print("SimulinkReceiver已停止")
