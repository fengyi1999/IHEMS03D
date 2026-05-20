"""
WebSocket服务器 - 向前端实时推送数据
"""
import json
import threading
import time
import os
from datetime import datetime, timedelta
from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO
import config
from chart_generator import ChartGenerator

class WebSocketServer:
    """
    WebSocket服务器类，用于处理与前端的实时通信
    """
    def __init__(self, debug=False, db_manager=None):
        """初始化WebSocket服务器

        参数:
            debug: 是否启用调试模式，控制日志输出
            db_manager: 数据库管理器实例，用于查询历史数据
        """
        # 获取项目根目录
        self.root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        self.frontend_dir = os.path.join(self.root_dir, 'frontend')

        self.app = Flask(__name__, static_folder=self.frontend_dir)
        # 允许跨域请求，增强CORS配置
        self.socketio = SocketIO(
            self.app, 
            cors_allowed_origins="*",
            logger=debug,
            engineio_logger=debug,
            async_mode='threading',
            # 明确指定Socket.IO的路径，避免与Flask路由冲突
            # 默认是 '/socket.io/'，这里显式指定以确保
            path='/socket.io/' 
        )
        self.running = False
        self.thread = None
        self.data_buffer = []  # 存储最近的数据
        self.buffer_size = 1800  # 保存30分钟数据(60秒*30)
        self.debug = debug  # 调试模式标志
        self.db_manager = db_manager  # 数据库管理器

        # 注册SocketIO事件处理函数
        self._register_handlers()

        # 注册路由
        self._register_routes()

    def _register_routes(self):
        """注册HTTP路由"""
        @self.app.route('/')
        def index():
            return send_from_directory(self.frontend_dir, 'index.html')

        @self.app.route('/<path:path>')
        def static_files(path):
            # 移除对Socket.IO路径的特殊处理，让SocketIO自行处理其内部路径
            return send_from_directory(self.frontend_dir, path)

    def _register_handlers(self):
        """注册SocketIO事件处理函数"""
        # 客户端连接事件
        @self.socketio.on('connect')
        def handle_connect():
            print(f'客户端已连接: {request.sid}')
            if self.debug:
                print(f'连接详情 - SID: {request.sid}, 远程地址: {request.environ.get("REMOTE_ADDR")}')
            # 发送缓冲区中的历史数据
            if self.data_buffer:
                # 缓冲区现在存储的是JSON字符串，需要手动构建一个JSON数组字符串
                history_json_string = '[' + ','.join(self.data_buffer) + ']'
                self.socketio.emit('history_data', history_json_string)
                if self.debug:
                    print(f'已向客户端 {request.sid} 发送 {len(self.data_buffer)} 条历史数据')

        # 客户端断开连接事件
        @self.socketio.on('disconnect')
        def handle_disconnect():
            print(f'客户端已断开连接: {request.sid}')
            if self.debug:
                print(f'断开连接详情 - SID: {request.sid}')

        # 客户端请求历史数据
        @self.socketio.on('get_history')
        def handle_get_history(data=None):
            # data参数是可选的，可能包含duration等参数
            # 目前直接返回缓冲区数据，后续可以根据data参数进行过滤
            # 缓冲区现在存储的是JSON字符串，需要手动构建一个JSON数组字符串
            history_json_string = '[' + ','.join(self.data_buffer) + ']'
            self.socketio.emit('history_data', history_json_string)

        # 客户端请求变量列表
        @self.socketio.on('get_variable_list')
        def handle_get_variable_list():
            # 生成变量列表
            variable_list = self._generate_variable_list()
            self.socketio.emit('variable_list', json.dumps(variable_list))

        # 客户端请求变量数据
        @self.socketio.on('get_variable_data')
        def handle_get_variable_data(data):
            try:
                # 解析请求数据
                request_data = json.loads(data)
                variable_names = request_data.get('variable_names', [])
                start_time = request_data.get('start_time')
                end_time = request_data.get('end_time')
                limit = request_data.get('limit', 1000)
                use_chart = request_data.get('use_chart', True)

                if self.debug:
                    print(f"请求变量数据: {variable_names}, 开始时间: {start_time}, 结束时间: {end_time}")

                # 校验变量名列表
                if not variable_names or not isinstance(variable_names, list) or len(variable_names) == 0:
                    self.socketio.emit('variable_data_result', json.dumps({
                        'error': '变量名称列表不能为空且必须是列表'
                    }))
                    return
                
                # 限制最大变量数量，避免处理过多数据
                max_variables = 20  # 设置最大变量数
                if len(variable_names) > max_variables:
                    print(f"变量数量超过限制: {len(variable_names)} > {max_variables}")
                    self.socketio.emit('variable_data_result', json.dumps({
                        'error': f'变量数量不能超过 {max_variables} 个'
                    }))
                    return

                # 查询变量数据
                variables_data_dict = {}
                has_data = False
                
                # 限制时间范围跨度，避免请求过大时间范围
                if start_time is not None and end_time is not None:
                    max_time_span = 7 * 24 * 3600  # 最大允许7天的数据
                    if end_time - start_time > max_time_span:
                        print(f"请求时间范围过大: {end_time - start_time} > {max_time_span}")
                        self.socketio.emit('variable_data_result', json.dumps({
                            'error': '时间范围不能超过7天，请缩小时间范围'
                        }))
                        return
                
                # 创建并行查询的线程列表
                query_threads = []
                import threading
                
                # 使用线程锁保护共享资源
                data_lock = threading.Lock()
                
                # 线程函数：查询单个变量的数据
                def query_variable_data(var_name):
                    nonlocal has_data
                    try:
                        variable_data = self._get_variable_data(
                            variable_name=var_name,
                            start_time=start_time,
                            end_time=end_time,
                            limit=limit
                        )
                        
                        # 使用锁保护共享资源的更新
                        with data_lock:
                            variables_data_dict[var_name] = variable_data
                            if variable_data:  # 检查是否有任何一个变量查询到了数据
                                has_data = True
                                
                        if self.debug:
                            print(f"变量 {var_name} 查询完成，获取 {len(variable_data)} 条数据")
                    except Exception as db_err:
                        print(f"查询变量 {var_name} 数据时出错: {db_err}")
                        with data_lock:
                            variables_data_dict[var_name] = []  # 出错时置为空列表
                
                # 创建并启动查询线程
                for variable_name in variable_names:
                    thread = threading.Thread(target=query_variable_data, args=(variable_name,))
                    thread.daemon = True
                    query_threads.append(thread)
                    thread.start()
                
                # 等待所有查询线程完成
                for thread in query_threads:
                    thread.join(timeout=10)  # 设置超时时间，避免无限等待
                
                # 准备响应数据
                response = {}

                # 合并数据为前端可用格式
                try:
                    merged_data = self._merge_variable_data(variables_data_dict)
                    response['data'] = merged_data
                except Exception as merge_err:
                    print(f"合并变量数据时出错: {merge_err}")
                    import traceback
                    traceback.print_exc()
                    self.socketio.emit('variable_data_result', json.dumps({
                        'error': f'合并数据时出错: {str(merge_err)}'
                    }))
                    return

                # 如果启用图表模式，并且至少有一个变量有数据，生成图表
                if use_chart and has_data:
                    try:
                        chart_option = ChartGenerator.generate_variable_chart(
                            variables_data_dict,
                            main_title=""  # 空标题
                        )
                        if chart_option:
                            response['chart'] = chart_option
                        else:
                            print(f"为变量 {variable_names} 生成图表失败")
                            response['chart'] = None
                    except Exception as chart_err:
                        import traceback
                        print(f"生成图表时发生异常: {chart_err}")
                        traceback.print_exc()
                        response['chart'] = None
                        self.socketio.emit('variable_data_result', json.dumps({
                            'error': f'生成图表时出错: {str(chart_err)}'
                        }))
                elif use_chart and not has_data:
                    # 如果请求了图表但所有变量都没数据
                    response['chart'] = None
                    print(f"为变量 {variable_names} 生成图表失败，所有变量均无数据")

                # 发送结果
                self.socketio.emit('variable_data_result', json.dumps(response))

            except Exception as e:
                import traceback
                print(f"处理变量数据请求时出错: {e}")
                traceback.print_exc()
                self.socketio.emit('variable_data_result', json.dumps({
                    'error': f"处理请求时出错: {str(e)}"
                }))

        # 客户端请求报表数据
        @self.socketio.on('get_variable_report_data')
        def handle_get_variable_report_data(data):
            try:
                # 解析请求数据
                if isinstance(data, str):
                    request_data = json.loads(data)
                else:
                    request_data = data

                variable_names = request_data.get('variable_names', [])
                start_time = request_data.get('start_time')
                end_time = request_data.get('end_time')

                if self.debug:
                    print(f"请求报表数据: {variable_names}, 开始时间: {start_time}, 结束时间: {end_time}")
                    print(f"变量数量: {len(variable_names)}")

                # 校验变量名列表
                if not variable_names or not isinstance(variable_names, list) or len(variable_names) == 0:
                    self.socketio.emit('variable_report_data_result', json.dumps({
                        'error': '变量名称列表不能为空且必须是列表'
                    }))
                    return

                # 限制最大变量数量，避免处理过多数据
                max_variables = 20  # 设置最大变量数
                if len(variable_names) > max_variables:
                    print(f"变量数量超过限制: {len(variable_names)} > {max_variables}")
                    self.socketio.emit('variable_report_data_result', json.dumps({
                        'error': f'变量数量不能超过 {max_variables} 个'
                    }))
                    return

                # 在单独线程中处理数据查询，避免阻塞主线程
                import threading
                
                def process_report_data():
                    try:
                        print(f"开始在工作线程中处理报表数据...")
                        
                        # 查询变量数据
                        variables_data_dict = {}
                        for variable_name in variable_names:
                            try:
                                variable_data = self._get_variable_data(
                                    variable_name=variable_name,
                                    start_time=start_time,
                                    end_time=end_time,
                                    limit=10000  # 报表数据通常需要更多数据点
                                )
                                variables_data_dict[variable_name] = variable_data
                                if self.debug:
                                    print(f"变量 {variable_name} 查询到 {len(variable_data)} 条数据")
                            except Exception as db_err:
                                print(f"查询变量 {variable_name} 报表数据时出错: {db_err}")
                                import traceback
                                traceback.print_exc()
                                variables_data_dict[variable_name] = []

                        # 检查是否有数据
                        data_count = sum(len(data) for data in variables_data_dict.values())
                        if data_count == 0:
                            print("所有变量均无数据")
                            try:
                                self.socketio.emit('variable_report_data_result', json.dumps({
                                    'error': '所选时间范围内无数据'
                                }))
                            except Exception as emit_err:
                                print(f"发送无数据响应时出错: {emit_err}")
                            return

                        # 合并数据为报表格式
                        print(f"开始合并报表数据...")
                        try:
                            report_data = self._merge_report_data(variables_data_dict)
                            print(f"报表数据合并完成，共 {len(report_data)} 条记录")
                        except Exception as merge_err:
                            print(f"合并报表数据时出错: {merge_err}")
                            import traceback
                            traceback.print_exc()
                            try:
                                self.socketio.emit('variable_report_data_result', json.dumps({
                                    'error': f"合并数据出错: {str(merge_err)}"
                                }))
                            except Exception:
                                pass
                            return

                        # 创建列定义
                        columns = [
                            {'key': 'timestamp', 'label': '时间戳'}
                        ]

                        # 为每个变量添加列定义
                        for variable_name in variable_names:
                            columns.append({
                                'key': variable_name,
                                'label': self._get_variable_label(variable_name)
                            })

                        # 限制返回的数据条数，避免数据过大
                        max_records = 5000
                        if len(report_data) > max_records:
                            print(f"报表数据过多，进行采样: {len(report_data)} -> {max_records}")
                            step = len(report_data) // max_records
                            report_data = report_data[::step][:max_records]

                        # 发送结果
                        print(f"准备发送报表数据，共 {len(report_data)} 条记录")
                        response = {
                            'data': report_data,
                            'columns': columns
                        }
                        try:
                            self.socketio.emit('variable_report_data_result', json.dumps(response))
                            print(f"报表数据发送完成")
                        except Exception as emit_err:
                            print(f"发送报表数据响应时出错: {emit_err}")
                            import traceback
                            traceback.print_exc()

                    except Exception as inner_e:
                        import traceback
                        print(f"工作线程中处理报表数据出错: {inner_e}")
                        traceback.print_exc()
                        
                        try:
                            self.socketio.emit('variable_report_data_result', json.dumps({
                                'error': f"处理请求时出错: {str(inner_e)}"
                            }))
                        except Exception as emit_err:
                            print(f"发送错误响应时出错: {emit_err}")
                            traceback.print_exc()
                
                # 创建并启动工作线程
                worker_thread = threading.Thread(target=process_report_data)
                worker_thread.daemon = True
                worker_thread.start()
                print(f"已创建工作线程处理报表数据请求")

            except Exception as e:
                import traceback
                print(f"处理报表数据请求时出错: {e}")
                traceback.print_exc()
                try:
                    self.socketio.emit('variable_report_data_result', json.dumps({
                        'error': f"处理请求时出错: {str(e)}"
                    }))
                except Exception as emit_err:
                    print(f"发送错误响应时出错: {emit_err}")
                    traceback.print_exc()

    def start(self):
        """启动WebSocket服务器"""
        if not self.running:
            self.running = True

            # 创建线程运行WebSocket服务器
            self.thread = threading.Thread(target=self._run_server)
            self.thread.daemon = True
            self.thread.start()

            print(f"WebSocket服务器已启动，地址: {config.WS_HOST}:{config.WS_PORT}")
            return True
        return False

    def _run_server(self):
        """在线程中运行WebSocket服务器"""
        # 确保此线程有自己的事件循环，以支持flask_socketio内部可能需要的异步操作
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        except Exception as e:
            print(f"设置事件循环出错: {e}")
        
        self.socketio.run(self.app, host=config.WS_HOST, port=config.WS_PORT)

    def send_data(self, json_data):
        """
        向所有连接的客户端发送数据

        参数:
            json_data: 要发送的数据，已经是JSON格式的字符串
        """
        if self.running:
            # 添加到历史数据缓冲区
            # 注意：现在缓冲区存储的是JSON字符串
            self.data_buffer.append(json_data)
            # 保持缓冲区大小
            if len(self.data_buffer) > self.buffer_size:
                self.data_buffer = self.data_buffer[-self.buffer_size:]

            # 在speed模式下优化数据发送
            if hasattr(config, 'SPEED') and config.SPEED > 1:
                # Speed模式下，减少缓冲区大小以节省内存，提高性能
                if len(self.data_buffer) > self.buffer_size // 2:
                    self.data_buffer = self.data_buffer[-(self.buffer_size // 2):]
                
                # Speed模式下不输出调试信息
                if self.debug and hasattr(config, 'SPEED') and config.SPEED <= 1:
                    # 只在非speed模式下输出调试信息
                    pass
            
            # 发送实时数据到所有客户端
            # 直接发送json_data，因为它已经是字符串了
            self.socketio.emit('realtime_data', json_data)

    def stop(self):
        """停止WebSocket服务器"""
        if self.running:
            self.running = False
            self.socketio.stop()
            if self.thread:
                self.thread.join(timeout=1)
            print("WebSocket服务器已停止")

    def _generate_variable_list(self):
        """
        生成变量列表

        Returns:
            list: 变量列表，每个变量包含name和label
        """
        # 基本系统变量
        system_variables = [
            {"name": "grid_power", "label": "电网功率 (MW)"},
            {"name": "grid_export_power", "label": "电网输出功率 (MW)"},
            {"name": "grid_import_power", "label": "电网输入功率 (MW)"},
            {"name": "grid_voltage", "label": "电网电压 (V)"},
            {"name": "grid_frequency", "label": "电网频率 (Hz)"},
            {"name": "solar_power", "label": "光伏功率 (MW)"},
            {"name": "wind_power", "label": "风电功率 (MW)"},
            {"name": "storage_power", "label": "储能功率 (MW)"},
            {"name": "hydrogen_real_power", "label": "制氢实际功率 (MW)"},
            {"name": "hydrogen_set_power", "label": "制氢设定功率 (MW)"},
            {"name": "hydrogen_production", "label": "产氢速率 (Nm³/h)"},
            {"name": "renewable_utilization", "label": "可再生能源利用率 (%)"},
            {"name": "green_energy_ratio", "label": "绿电比例 (%)"},
            {"name": "system_runtime", "label": "系统运行时间 (h)"}
        ]

        # 电解槽变量
        electrolyzer_variables = []
        for i in range(1, 21):  # 20个电解槽
            electrolyzer_variables.extend([
                {"name": f"electrolyzer_status_{i}", "label": f"电解槽{i}状态"},
                {"name": f"electrolyzer_set_power_{i}", "label": f"电解槽{i}设定功率 (MW)"},
                {"name": f"electrolyzer_real_power_{i}", "label": f"电解槽{i}实际功率 (MW)"},
                {"name": f"hydrogen_rate_{i}", "label": f"电解槽{i}产氢速率 (Nm³/h)"},
                {"name": f"electrolyzer_temp_{i}", "label": f"电解槽{i}温度 (°C)"}
            ])

        # 合并所有变量
        all_variables = system_variables + electrolyzer_variables

        return all_variables

    def _get_variable_data(self, variable_name, start_time=None, end_time=None, limit=1000):
        """
        获取变量数据

        Args:
            variable_name: 变量名
            start_time: 开始时间戳
            end_time: 结束时间戳
            limit: 最大数据点数

        Returns:
            list: 变量数据列表，每个数据点包含timestamp和value
        """
        # 如果有数据库管理器，使用数据库查询
        if self.db_manager:
            try:
                return self.db_manager.get_variable_data(
                    variable_name=variable_name,
                    start_time=start_time,
                    end_time=end_time,
                    limit=limit
                )
            except Exception as e:
                print(f"数据库查询变量 {variable_name} 失败: {e}")
                # 如果数据库查询失败，尝试从内存中获取
                pass

        # 从内存数据缓冲区中提取数据
        result = []

        # 确定时间范围
        if start_time is None:
            # 默认查询最近1小时的数据
            start_time = int(time.time()) - 3600
        if end_time is None:
            end_time = int(time.time())

        # 从数据缓冲区中提取数据
        try:
            for data_point_json in self.data_buffer:
                try:
                    # 由于缓冲区现在存储JSON字符串，需要先解析
                    data_point = json.loads(data_point_json)
                    timestamp = data_point.get('timestamp', 0)

                    # 检查时间范围
                    if timestamp < start_time or timestamp > end_time:
                        continue

                    # 提取变量值
                    value = None
                    data_content = data_point.get('data', {})

                    # 处理系统变量
                    if variable_name in data_content:
                        value = data_content[variable_name]

                    # 处理电解槽变量
                    elif variable_name.startswith('electrolyzer_') or variable_name.startswith('hydrogen_rate_'):
                        # 解析电解槽索引
                        parts = variable_name.split('_')
                        if len(parts) >= 3 and parts[-1].isdigit():
                            index = int(parts[-1]) - 1  # 转换为0基索引

                            # 根据变量名前缀确定基础名称
                            if variable_name.startswith('electrolyzer_status_'):
                                base_name = 'electrolyzer_status'
                            elif variable_name.startswith('electrolyzer_set_power_'):
                                base_name = 'electrolyzer_set_power'
                            elif variable_name.startswith('electrolyzer_real_power_'):
                                base_name = 'electrolyzer_real_power'
                            elif variable_name.startswith('hydrogen_rate_'):
                                base_name = 'hydrogen_rate'
                            elif variable_name.startswith('electrolyzer_temp_'):
                                base_name = 'electrolyzer_temp'
                            else:
                                base_name = '_'.join(parts[:-1])

                            # 从数组中获取值
                            if base_name in data_content and isinstance(data_content[base_name], list):
                                if 0 <= index < len(data_content[base_name]):
                                    value = data_content[base_name][index]

                    # 处理带点号的变量名 (例如 electrolyzer_status.0)
                    elif '.' in variable_name:
                        try:
                            base_name, index_str = variable_name.split('.')
                            index = int(index_str)

                            if base_name in data_content and isinstance(data_content[base_name], list):
                                if 0 <= index < len(data_content[base_name]):
                                    value = data_content[base_name][index]
                        except (ValueError, IndexError, TypeError) as e:
                            print(f"处理带点号的变量 {variable_name} 时出错: {e}")
                            continue

                    # 添加到结果集
                    if value is not None:
                        result.append({
                            'timestamp': timestamp,
                            'value': value
                        })
                except Exception as inner_e:
                    print(f"处理数据点时出错: {inner_e}")
                    continue
                
            # 限制结果集大小
            if len(result) > limit:
                # 均匀采样
                step = len(result) // limit
                result = result[::step][:limit]
                
        except GeneratorExit:
            print(f"_get_variable_data 协程被中断，已安全处理")
            # 返回已收集的结果
            return result
        except Exception as e:
            print(f"_get_variable_data 处理出错: {e}")
            import traceback
            traceback.print_exc()

        return result

    def _merge_variable_data(self, variables_data_dict):
        """
        将多个变量的时间序列数据合并为前端可用的格式

        Args:
            variables_data_dict: 变量数据字典，格式为 {变量名: [{timestamp: 时间戳, value: 值}, ...], ...}

        Returns:
            list: 合并后的数据列表，每个元素包含时间戳和所有变量的值
        """
        if not variables_data_dict:
            return []

        # 创建时间戳到数据的映射
        timestamp_to_data = {}

        # 遍历每个变量的数据
        for variable_name, data_list in variables_data_dict.items():
            for data_point in data_list:
                timestamp = data_point['timestamp']
                value = data_point['value']

                # 确保时间戳存在于映射中
                if timestamp not in timestamp_to_data:
                    timestamp_to_data[timestamp] = {'timestamp': timestamp}

                # 添加变量值
                timestamp_to_data[timestamp][variable_name] = value

        # 转换为列表并按时间戳排序
        result = list(timestamp_to_data.values())
        result.sort(key=lambda x: x['timestamp'])

        return result

    def _merge_report_data(self, variables_data_dict):
        """
        将多个变量的时间序列数据合并为报表格式

        Args:
            variables_data_dict: 变量数据字典，格式为 {变量名: [{timestamp: 时间戳, value: 值}, ...], ...}

        Returns:
            list: 合并后的报表数据列表
        """
        if not variables_data_dict:
            return []

        try:
            # 检查数据量，防止处理过多数据
            total_data_points = sum(len(data) for data in variables_data_dict.values())
            print(f"合并报表数据，总数据点数: {total_data_points}")
            
            # 如果数据点过多，进行预采样
            max_points_per_variable = 2000
            for variable_name, data_list in variables_data_dict.items():
                if len(data_list) > max_points_per_variable:
                    step = len(data_list) // max_points_per_variable
                    if step > 1:
                        print(f"变量 {variable_name} 数据点过多 ({len(data_list)}), 进行预采样, 步长: {step}")
                        variables_data_dict[variable_name] = data_list[::step]

            # 使用字典优化时间戳搜索
            # 创建时间戳到数据的映射
            timestamp_data_map = {}

            # 收集所有时间戳并为每个时间戳准备数据容器
            all_timestamps = set()
            for variable_name, data_list in variables_data_dict.items():
                try:
                    for data_point in data_list:
                        timestamp = data_point['timestamp']
                        all_timestamps.add(timestamp)
                        
                        # 初始化时间戳数据映射
                        if timestamp not in timestamp_data_map:
                            timestamp_data_map[timestamp] = {'timestamp': timestamp}
                except GeneratorExit:
                    print(f"收集时间戳时收到中断信号，中断处理")
                    # 返回已处理的数据
                    break
                except Exception as e:
                    print(f"收集时间戳时出错: {e}")
                    # 继续处理其他变量

            # 填充变量数据
            for variable_name, data_list in variables_data_dict.items():
                try:
                    # 为这个变量创建时间戳到值的映射，以加速查找
                    timestamp_to_value = {point['timestamp']: point['value'] for point in data_list}
                    
                    # 为每个收集到的时间戳添加这个变量的值
                    for timestamp in all_timestamps:
                        timestamp_data_map[timestamp][variable_name] = timestamp_to_value.get(timestamp)
                except GeneratorExit:
                    print(f"填充变量 {variable_name} 数据时收到中断信号，中断处理")
                    break
                except Exception as e:
                    print(f"填充变量 {variable_name} 数据时出错: {e}")
                    # 继续处理其他变量

            # 将映射转换为列表并排序
            report_data = list(timestamp_data_map.values())
            report_data.sort(key=lambda x: x['timestamp'])
            
            print(f"报表数据合并完成，共 {len(report_data)} 条记录")
            
            return report_data
            
        except GeneratorExit:
            print(f"_merge_report_data 协程被中断，已安全处理")
            # 返回已收集的数据
            if timestamp_data_map:
                report_data = list(timestamp_data_map.values())
                report_data.sort(key=lambda x: x['timestamp'])
                return report_data
            return []
        except Exception as e:
            print(f"_merge_report_data 处理出错: {e}")
            import traceback
            traceback.print_exc()
            # 返回已收集的数据或空列表
            if timestamp_data_map:
                try:
                    report_data = list(timestamp_data_map.values())
                    report_data.sort(key=lambda x: x['timestamp'])
                    return report_data
                except:
                    pass
            return []

    def _get_variable_label(self, variable_name):
        """
        获取变量的显示标签

        Args:
            variable_name: 变量名称

        Returns:
            str: 变量的显示标签
        """
        # 变量名到标签的映射
        variable_labels = {
            "grid_power": "电网功率 (MW)",
            "grid_export_power": "电网输出功率 (MW)",
            "grid_import_power": "电网输入功率 (MW)",
            "grid_voltage": "电网电压 (V)",
            "grid_frequency": "电网频率 (Hz)",
            "solar_power": "光伏功率 (MW)",
            "wind_power": "风电功率 (MW)",
            "storage_power": "储能功率 (MW)",
            "hydrogen_real_power": "制氢实际功率 (MW)",
            "hydrogen_set_power": "制氢设定功率 (MW)",
            "hydrogen_production": "产氢速率 (Nm³/h)",
            "renewable_utilization": "可再生能源利用率 (%)",
            "green_energy_ratio": "绿电比例 (%)",
            "system_runtime": "系统运行时间 (h)"
        }

        # 处理电解槽变量
        if variable_name.startswith('electrolyzer_status_'):
            index = variable_name.split('_')[-1]
            return f"电解槽{index}状态"
        elif variable_name.startswith('electrolyzer_set_power_'):
            index = variable_name.split('_')[-1]
            return f"电解槽{index}设定功率 (MW)"
        elif variable_name.startswith('electrolyzer_real_power_'):
            index = variable_name.split('_')[-1]
            return f"电解槽{index}实际功率 (MW)"
        elif variable_name.startswith('hydrogen_rate_'):
            index = variable_name.split('_')[-1]
            return f"电解槽{index}产氢速率 (Nm³/h)"
        elif variable_name.startswith('electrolyzer_temp_'):
            index = variable_name.split('_')[-1]
            return f"电解槽{index}温度 (°C)"

        # 处理带点号的电解槽变量 (例如 electrolyzer_status.0)
        if '.' in variable_name:
            try:
                base_name, index = variable_name.split('.')
                idx = int(index) + 1
                if base_name == 'electrolyzer_real_power':
                    return f'电解槽{idx}实时功率 (MW)'
                elif base_name == 'electrolyzer_set_power':
                    return f'电解槽{idx}给定功率 (MW)'
                elif base_name == 'hydrogen_rate':
                    return f'电解槽{idx}产氢速率 (Nm³/h)'
                elif base_name == 'electrolyzer_temp':
                    return f'电解槽{idx}温度 (℃)'
                elif base_name == 'electrolyzer_status':
                    return f'电解槽{idx}状态'
            except Exception as e:
                print(f"处理带点号的变量标签 {variable_name} 时出错: {e}")
                pass

        # 返回映射的标签或原始变量名
        return variable_labels.get(variable_name, variable_name)


# 测试代码
if __name__ == "__main__":
    # 创建WebSocket服务器
    ws_server = WebSocketServer()
    ws_server.start()

    # 模拟发送一些测试数据
    try:
        for i in range(10):
            # 创建测试数据
            test_data = {
                'timestamp': int(time.time()),
                'data': {
                    'power': 150.0 + i * 2,
                    'voltage': 220.0 + i * 0.5,
                    'current': 0.7 + i * 0.1
                }
            }

            # 发送数据
            ws_server.send_data(test_data)
            print(f"已发送测试数据 #{i+1}")
            time.sleep(1)

        # 保持服务器运行
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("程序中断")
        ws_server.stop()
