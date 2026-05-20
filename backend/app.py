"""
主应用程序入口 - 整合各个模块并启动服务
"""
import time
import threading
import json
import config
from simulink_receiver import SimulinkReceiver
from websocket_server import WebSocketServer
from db_manager import DatabaseManager
import argparse # 导入 argparse
import signal
import sys
import io
import os

# 设置标准输出编码为UTF-8，解决中文输出问题
if sys.platform == 'win32':
    # Windows平台特殊处理
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

def signal_handler(signum, frame):
    """信号处理函数"""
    print("\n接收到终止信号")
    if 'ems' in globals():
        ems.stop()
    sys.exit(0)

class EnergyManagementSystem:
    """
    能源管理系统主类 - 协调各个模块的工作
    """
    def __init__(self, test=False): # 默认非测试模式
        """初始化能源管理系统"""
        self.test = test # 存储测试模式标志
        # 创建数据库管理器
        self.db_manager = DatabaseManager()

        # 创建WebSocket服务器，传递测试模式标志和数据库管理器
        self.ws_server = WebSocketServer(debug=self.test, db_manager=self.db_manager) # 直接使用布尔值

        # 创建Simulink接收器，并设置回调函数，传递测试模式标志
        self.simulink_receiver = SimulinkReceiver(data_callback=self.handle_data, test=self.test)

        # 系统运行标志
        self.running = False

        # 累计产氢量 (Nm³)
        self.total_hydrogen_production = 0

        # 上网电量累计值 (MWh)
        self.grid_export_energy = 0

        # 下网电量累计值 (MWh)
        self.grid_import_energy = 0

        # 风电发电量累计值 (MWh)
        self.wind_energy = 0

        # 光伏发电量累计值 (MWh)
        self.solar_energy = 0

        # 系统运行时间 (秒)
        self.system_runtime = 0

        # 系统启动时间（将在start方法中设置）
        self.start_timestamp = None

        # 上次更新时间
        self.last_update_time = None

    def handle_data(self, data):
        """
        处理收到的数据

        参数:
            data: 从Simulink接收到的数据或模拟数据
        """
        try:
            # 处理电解槽矩阵数据，计算系统信息和设备状态统计
            if 'data' in data:
                data_content = data['data']

                # 处理电解槽矩阵数据
                if 'electrolyzer_status' in data_content and 'electrolyzer_real_power' in data_content and 'hydrogen_rate' in data_content:
                    # 计算系统信息区域变量
                    system_info = self.calculate_system_info(data_content)

                    # 计算设备状态统计区域变量
                    device_stats = self.calculate_device_stats(data_content)

                    # 将计算结果添加到数据中
                    data_content['system_info'] = system_info
                    data_content['device_stats'] = device_stats

                    # 将系统信息区域变量移到顶层数据中
                    data_content['hydrogen_power'] = system_info['hydrogen_power']
                    data_content['production_rate'] = system_info['production_rate']
                    data_content['energy_consumption'] = system_info['energy_consumption']
                    data_content['total_production'] = system_info['total_production']
                    data_content['uplink_power'] = system_info['uplink_power']
                    data_content['downlink_power'] = system_info['downlink_power']
                    data_content['grid_export_energy'] = system_info['grid_export_energy']
                    data_content['grid_import_energy'] = system_info['grid_import_energy']
                    data_content['wind_energy'] = system_info['wind_energy']
                    data_content['solar_energy'] = system_info['solar_energy']
                    data_content['wind_utilization_rate'] = system_info['wind_utilization_rate']
                    data_content['solar_utilization_rate'] = system_info['solar_utilization_rate']
                    data_content['green_electricity_ratio'] = system_info['green_electricity_ratio']
                    data_content['system_runtime'] = system_info['system_runtime']

                    # 将设备状态统计区域变量移到顶层数据中
                    data_content['running_count'] = device_stats['running_count']
                    data_content['standby_count'] = device_stats['standby_count']
                    data_content['shutdown_count'] = device_stats['shutdown_count']
                    data_content['maintenance_count'] = device_stats['maintenance_count']
                    data_content['cold_start_count'] = device_stats['cold_start_count']
                    data_content['hot_start_count'] = device_stats['hot_start_count']
                    data_content['hot_standby_count'] = device_stats['hot_standby_count']
                    data_content['idle_count'] = device_stats['idle_count']

            # 添加仿真时间戳和速度信息
            if 'timestamp' in data:
                data['sim_time'] = data['timestamp']  # 使用真实时间戳
            
            # 添加仿真速度信息
            data['speed'] = config.SPEED

            # 序列化数据为JSON字符串
            json_data = json.dumps(data)

            # 使用WebSocket向前端发送数据
            self.ws_server.send_data(json_data)

            # 根据SAVE_DATA配置决定是否保存数据
            if config.SAVE_DATA:
                # 保存数据到数据库或内存缓存
                if hasattr(self, 'db_manager'):
                    # 如果数据库管理器存在，就使用它来保存数据
                    save_result = self.db_manager.save_data(data)
                    if self.test and save_result:
                        print(f"数据已{'保存到数据库' if not self.db_manager.no_db_mode else '保存到内存缓存'}")
            elif self.test:
                print("接收到数据，但由于 SAVE_DATA=False 而不保存")
            
            # Speed模式下的简化输出 - 完全静默，只在出错时输出
            if config.SPEED > 1:
                # Speed模式下不输出任何常规信息，保证性能
                pass
            elif self.test:
                # 只有在test模式下才输出详细信息
                self.print_data(data)
            else:
                # 普通模式下输出基本信息
                if 'timestamp' in data:
                    print(f"数据接收 - 时间戳: {data['timestamp']}")
                else:
                    print("数据接收")

        except Exception as e:
            import traceback
            print(f"处理数据时出错: {e}")
            print(traceback.format_exc())

    def print_data(self, data):
        """
        打印数据到终端（测试模式使用）

        参数:
            data: 要打印的数据
        """
        print("\n" + "="*50)
        print("WebSocket发送数据 - 时间戳:", data.get('timestamp', 'N/A'))
        print("-"*50)

        if 'data' in data:
            print("数据内容:")
            data_content = data['data']

            # 只打印SimSend.py发送的六个单值数据
            print("\n单值数据:")
            # 显示SimSend3.py发送的九个单值数据
            single_values = [
                'wind_power',           # 风电实时出力
                'solar_power',          # 光伏实时出力
                'fess_power',           # 构网储能
                'bess_power',           # 跟网储能
                'grid_power',           # 电网实时功率
                'hydrogen_total_power', # 制氢总功率
                'hydrogen_load',        # 供氢负载
                'hydrogen_soc',         # 储氢SOH
                'hydrogen_hss'          # 储氢罐充放氢气速率
            ]

            for key in single_values:
                if key in data_content:
                    print(f"{key}: {data_content[key]}")

            # 打印矩阵数据
            matrix_keys = [
                'electrolyzer_status', 'electrolyzer_set_power', 'hydrogen_rate',
                'electrolyzer_real_power', 'electrolyzer_temp'
            ]

            print("\n矩阵数据:")
            for key in matrix_keys:
                if key in data_content and isinstance(data_content[key], list):
                    print(f"{key}: {data_content[key][:3]}... (共{len(data_content[key])}个值)")

            # 打印系统信息
            if 'system_info' in data_content:
                print("\n系统信息:")
                for key, value in data_content['system_info'].items():
                    print(f"{key}: {value}")

            # 打印设备状态统计
            if 'device_stats' in data_content:
                print("\n设备状态统计:")
                for key, value in data_content['device_stats'].items():
                    print(f"{key}: {value}")

        print("="*50)

    def start(self):
        """启动能源管理系统"""
        if self.running:
            print("系统已经在运行")
            return False

        print("正在启动智慧绿氢管理系统...")
        print(f"当前配置的TCP端口: {config.TCP_PORT}")
        print(f"当前配置的WebSocket端口: {config.WS_PORT}")
        print(f"模拟数据模式: {config.SIMULATE_DATA}")
        print(f"无数据库模式: {config.NO_DB}")
        print(f"保存数据: {config.SAVE_DATA}")

        # 立即打印一条可能被run.py捕获的消息
        print("服务器已准备就绪")

        # 连接到数据库
        print("正在连接数据库...")
        db_connected = self.db_manager.connect()
        if db_connected:
            print("数据库连接成功")
        else:
            print("警告: 数据库连接失败，将以无数据库模式运行")

        # 启动WebSocket服务器
        print("正在启动WebSocket服务器...")
        ws_started = self.ws_server.start()
        if not ws_started:
            print("错误: WebSocket服务器启动失败")
            return False
        print(f"WebSocket服务器启动成功, 地址: http://127.0.0.1:{config.WS_PORT}")

        # 检查WebSocket端口是否已开放
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', config.WS_PORT))
            if result == 0:
                print(f"WebSocket端口 {config.WS_PORT} 已开放")
            else:
                print(f"警告: WebSocket端口 {config.WS_PORT} 未开放，前端可能无法连接")
            sock.close()
        except Exception as e:
            print(f"检查WebSocket端口时出错: {e}")

        # 启动Simulink接收器或模拟器
        if config.SIMULATE_DATA:
            print("正在启动模拟数据生成器...")
            sim_started = self.simulink_receiver.start_simulator()
            if not sim_started:
                print("错误: 模拟数据生成器启动失败")
                return False
            print("模拟数据生成器启动成功")
        else:
            print(f"正在启动TCP服务器，端口:{config.TCP_PORT}...")
            tcp_started = self.simulink_receiver.start_tcp_server()
            if not tcp_started:
                print("错误: TCP服务器启动失败")
                # 尝试启动临时模拟数据生成器
                print("尝试启动临时模拟数据生成器...")
                sim_started = self.simulink_receiver.start_simulator()
                if not sim_started:
                    print("错误: 临时模拟数据生成器启动失败")
                    return False
                print("临时模拟数据生成器启动成功")
            else:
                print("TCP服务器启动成功")

        # 设置系统启动时间（在所有服务启动完成后）
        self.start_timestamp = time.time()
        
        self.running = True
        print("智慧绿氢管理系统已启动")
        return True

    def calculate_system_info(self, data_content):
        """
        计算系统信息区域变量

        参数:
            data_content: 数据内容

        返回:
            包含系统信息变量的字典
        """
        # 获取电解槽状态和功率矩阵
        electrolyzer_status = data_content.get('electrolyzer_status', [])
        electrolyzer_real_power = data_content.get('electrolyzer_real_power', [])
        hydrogen_rate = data_content.get('hydrogen_rate', [])

        # 获取单值变量
        wind_power = data_content.get('wind_power', 0)
        solar_power = data_content.get('solar_power', 0)
        grid_power = data_content.get('grid_power', 0)
        hydrogen_total_power = data_content.get('hydrogen_total_power', 0)
        hydrogen_load = data_content.get('hydrogen_load', 0)
        hydrogen_soc = data_content.get('hydrogen_soc', 0)
        hydrogen_hss = data_content.get('hydrogen_hss', 0)

        # 关联电网功率与上下网功率
        if grid_power > 0:
            # 正值表示从电网输入电力（下网）
            downlink_power = grid_power
            uplink_power = 0
        else:
            # 负值表示向电网输出电力（上网）
            downlink_power = 0
            uplink_power = abs(grid_power)

        # 计算时间差
        current_time = time.time()
        elapsed_seconds = 0
        elapsed_hours = 0

        if self.last_update_time is not None:
            elapsed_seconds = current_time - self.last_update_time
            elapsed_hours = elapsed_seconds / 3600  # 转换为小时

            # 累计上网电量 (MWh)
            self.grid_export_energy += uplink_power * elapsed_hours

            # 累计下网电量 (MWh)
            self.grid_import_energy += downlink_power * elapsed_hours

            # 累计风电发电量 (MWh)
            self.wind_energy += wind_power * elapsed_hours

            # 累计光伏发电量 (MWh)
            self.solar_energy += solar_power * elapsed_hours

        # 计算系统运行时间 - 始终使用真实项目运行时间
        if self.start_timestamp is not None:
            # 无论是否处于速度模式，都使用真实的项目运行时间
            self.system_runtime = int(current_time - self.start_timestamp)
        else:
            # 如果还没有设置启动时间，运行时间为0
            self.system_runtime = 0

        # 确保列表长度相同
        min_length = min(len(electrolyzer_status), len(electrolyzer_real_power), len(hydrogen_rate))

        # 根据新的状态值定义：
        # 状态值 0 表示检修
        # 状态值 1 表示冷备待机
        # 状态值 2 3 4 均表示冷启动
        # 状态值 5 表示热备
        # 状态值 6 表示热启动
        # 状态值 7 表示运行

        # 运行状态的电解槽索引（状态值7表示运行）
        running_indices = [i for i in range(min_length) if electrolyzer_status[i] == 7]

        # 冷启动状态的电解槽索引（状态值2,3,4表示冷启动）
        cold_start_indices = [i for i in range(min_length) if electrolyzer_status[i] in [2, 3, 4]]

        # 热启动状态的电解槽索引（状态值6表示热启动）
        hot_start_indices = [i for i in range(min_length) if electrolyzer_status[i] == 6]

        # 所有有功率的电解槽索引（运行、冷启动和热启动）
        active_indices = running_indices + cold_start_indices + hot_start_indices

        # 计算制氢功率 (MW) - 所有运行、冷启动和热启动状态的电解槽实际功率总和
        hydrogen_power = sum(electrolyzer_real_power[i] for i in active_indices) if active_indices else 0

        # 计算产氢速率 (Nm³/h) - 所有运行、冷启动和热启动状态的电解槽产氢速率总和
        production_rate = sum(hydrogen_rate[i] for i in active_indices) if active_indices else 0

        # 调试输出（仅在测试模式下打印）
        if self.test == 1:
            print(f"电解槽状态: {electrolyzer_status}")
            print(f"电解槽实际功率: {electrolyzer_real_power}")
            print(f"运行状态的电解槽索引: {running_indices}")
            print(f"冷启动状态的电解槽索引: {cold_start_indices}")
            print(f"热启动状态的电解槽索引: {hot_start_indices}")
            print(f"所有有功率的电解槽索引: {active_indices}")
            print(f"制氢功率: {hydrogen_power} MW")
            print(f"产氢速率: {production_rate} Nm³/h")

        # 计算制氢能耗 (MWh/Nm³) - 总功率除以总产氢速率
        if production_rate > 0:
            energy_consumption = hydrogen_power / production_rate
        else:
            energy_consumption = 0

        # 更新累计产氢量 (Nm³)
        if self.last_update_time is not None:
            self.total_hydrogen_production += production_rate * elapsed_hours

        # 计算风电利用率
        renewable_power = wind_power + solar_power
        wind_utilization_rate = 0
        solar_utilization_rate = 0
        green_electricity_ratio = 0

        # 计算风电和光伏利用率 - 实际计算使风力发电和光伏发电上网或用于制氢的百分比
        if wind_power > 0:
            wind_utilization_rate = min(100, (wind_power - max(0, renewable_power - hydrogen_power - uplink_power)) / wind_power * 100)

        if solar_power > 0:
            solar_utilization_rate = min(100, (solar_power - max(0, renewable_power - hydrogen_power - uplink_power)) / solar_power * 100)

        # 计算绿电比率 - 可再生能源占制氢能源的百分比
        if hydrogen_power > 0:
            green_electricity_ratio = min(100, (renewable_power - max(0, renewable_power - hydrogen_power)) / hydrogen_power * 100)

        # 更新上次处理时间
        self.last_update_time = current_time

        # 返回计算结果
        return {
            'hydrogen_power': round(hydrogen_power, 2),
            'production_rate': round(production_rate, 2),
            'energy_consumption': round(energy_consumption, 2),
            'total_production': round(self.total_hydrogen_production, 2),
            'downlink_power': round(downlink_power, 2),
            'uplink_power': round(uplink_power, 2),
            'grid_import_energy': round(self.grid_import_energy, 2),
            'grid_export_energy': round(self.grid_export_energy, 2),
            'wind_energy': round(self.wind_energy, 2),
            'solar_energy': round(self.solar_energy, 2),
            'wind_utilization_rate': round(wind_utilization_rate, 2),
            'solar_utilization_rate': round(solar_utilization_rate, 2),
            'green_electricity_ratio': round(green_electricity_ratio, 2),
            'system_runtime': self.system_runtime,
            'hydrogen_load': round(hydrogen_load, 2),
            'hydrogen_soc': round(hydrogen_soc, 2),
            'hydrogen_hss': round(hydrogen_hss, 2)
        }

    def calculate_device_stats(self, data_content):
        """
        计算设备状态统计区域变量

        参数:
            data_content: 数据内容

        返回:
            包含设备状态统计变量的字典
        """
        # 获取电解槽状态矩阵
        electrolyzer_status = data_content.get('electrolyzer_status', [])

        # 定义状态计数
        maintenance_count = 0  # 检修数量 (状态值 0)
        cold_standby_count = 0 # 冷备待机数量 (状态值 1)
        cold_start_count = 0   # 冷启动数量 (状态值 2,3,4)
        hot_standby_count = 0  # 热备数量 (状态值 5)
        hot_start_count = 0    # 热启动数量 (状态值 6)
        running_count = 0      # 运行数量 (状态值 7)
        idle_count = 0         # 待命数量 (特殊状态，暂不统计)

        # 严格按照电解槽状态值统计各状态数量
        # 状态值 0 表示检修
        # 状态值 1 表示冷备待机
        # 状态值 2 3 4 均表示冷启动
        # 状态值 5 表示热备
        # 状态值 6 表示热启动
        # 状态值 7 表示运行
        for status in electrolyzer_status:
            if status == 0:
                maintenance_count += 1
            elif status == 1:
                cold_standby_count += 1
            elif status in [2, 3, 4]:
                cold_start_count += 1
            elif status == 5:
                hot_standby_count += 1
            elif status == 6:
                hot_start_count += 1
            elif status == 7:
                running_count += 1

        # 调试输出（仅在测试模式下打印）
        if self.test == 1:
            print(f"电解槽状态统计: 检修={maintenance_count}, 冷备待机={cold_standby_count}, 冷启动={cold_start_count}, 热备={hot_standby_count}, 热启动={hot_start_count}, 运行={running_count}")

        # 返回计算结果
        return {
            'running_count': running_count,          # 运行数量 (状态值 7)
            'standby_count': cold_standby_count + hot_standby_count, # 待机数量
            'shutdown_count': cold_standby_count,     # 停机（冷备）数量 (状态值 1)
            'hot_standby_count': hot_standby_count,     # 热备数量 (状态值 5)
            'maintenance_count': maintenance_count,  # 检修数量 (状态值 0)
            'cold_start_count': cold_start_count,    # 冷启动数量 (状态值 2,3,4)
            'hot_start_count': hot_start_count,      # 热启动数量 (状态值 6)
            'idle_count': 0                          # 待命数量 (特殊状态，暂不统计)
        }

    def stop(self):
        """停止能源管理系统"""
        if not self.running:
            print("系统未在运行")
            return

        print("正在停止智慧绿氢管理系统...")

        # 停止Simulink接收器
        self.simulink_receiver.stop()

        # 停止WebSocket服务器
        self.ws_server.stop()

        # 断开数据库连接
        self.db_manager.disconnect()

        self.running = False
        print("智慧绿氢管理系统已停止")


# 主函数
if __name__ == "__main__":
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 使用 argparse 解析命令行参数
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', help='Enable test mode')
    args = parser.parse_args()

    if args.test:
        print("测试模式已启用: 将打印更多调试信息")

    # 创建能源管理系统实例，传递测试模式标志
    ems = EnergyManagementSystem(test=args.test)

    # 启动系统
    if ems.start():
        try:
            # 保持主线程运行
            print("系统运行中，按Ctrl+C停止...")
            while ems.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n接收到终止信号")
        finally:
            # 停止系统
            ems.stop()
    else:
        print("系统启动失败")
