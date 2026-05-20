import socket
import struct
import time
import random
import numpy as np
import threading
import json
import os
from datetime import datetime
import sys
import traceback
import logging
import subprocess
import re
import psutil
import signal

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('simsend3.log'),
        logging.StreamHandler()
    ]
)

# 配置参数
TCP_HOST = '127.0.0.1'  # 本地主机
TCP_PORT = 14001  # TCP服务器端口
RECORD_PORT = 14002  # 录波服务器端口

def find_process_using_port(port):
    """查找占用指定端口的进程"""
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                connections = proc.connections()
                for conn in connections:
                    if conn.laddr.port == port:
                        return proc.info['pid'], proc.info['name']
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                continue
        return None, None
    except Exception as e:
        logging.error(f"查找端口进程时出错: {str(e)}")
        return None, None

def kill_process_by_pid(pid, process_name=None):
    """根据PID结束进程"""
    try:
        process = psutil.Process(pid)
        process.terminate()
        
        try:
            process.wait(timeout=3)
        except psutil.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=3)
            except psutil.TimeoutExpired:
                subprocess.run(['taskkill', '/F', '/PID', str(pid)], 
                             capture_output=True, text=True)
        
        return True
    except psutil.NoSuchProcess:
        return True
    except Exception as e:
        logging.error(f"结束进程时出错: {str(e)}")
        return False

def cleanup_port(port):
    """清理端口"""
    pid, process_name = find_process_using_port(port)
    if pid:
        logging.info(f"清理占用端口的进程: {process_name} (PID: {pid})")
        return kill_process_by_pid(pid, process_name)
    return True

class SimSend3:
    def __init__(self, host=TCP_HOST, port=TCP_PORT, cc_mode=False, speed=1):
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        self.thread = None
        self.recorded_data = []
        self.current_index = 0
        self.cc_mode = cc_mode
        self.speed = speed
        self.delay = 1.0 / self.speed if self.speed > 0 else 1.0
        
        # 录波相关
        self.recording = False
        self.record_server = None
        self.record_thread = None
        self.record_data = []
        self.record_start_time = None
        
        # 初始化数据 - 9个单变量
        self.single_values = [0.0] * 9
        self.matrices = [[0.0] * 20 for _ in range(5)]
        
        # 数据目录
        self.data_dir = 'data'
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        
    def load_latest_data(self):
        """加载最新的记录数据"""
        try:
            if not os.path.exists(self.data_dir):
                logging.error(f"数据目录 {self.data_dir} 不存在")
                return False
                
            files = [f for f in os.listdir(self.data_dir) if f.endswith('.json')]
            if not files:
                logging.error("未找到JSON数据文件")
                return False
                
            latest_file = max(files)
            file_path = os.path.join(self.data_dir, latest_file)
            
            with open(file_path, 'r') as f:
                self.recorded_data = json.load(f)
            logging.info(f"已加载数据文件: {latest_file}, 包含 {len(self.recorded_data)} 条记录")
            return True
        except Exception as e:
            logging.error(f"加载数据文件时出错: {str(e)}")
            return False
            
    def generate_data(self):
        """从记录的数据中生成数据，并在数据读取完后循环从头读取"""
        if not self.recorded_data:
            return
            
        if self.current_index >= len(self.recorded_data):
            logging.info("JSON数据已读取完毕，将从头开始循环读取。")
            self.current_index = 0
            
        try:
            data = self.recorded_data[self.current_index]
            self.current_index += 1
            
            # 直接使用从JSON加载的完整single_values
            self.single_values = data.get('single_values', [0.0] * 9)
            if len(self.single_values) < 9:
                self.single_values.extend([0.0] * (9 - len(self.single_values)))
            
            source_matrices = data['matrices']

            # 适配16或20个电解槽数据，统一填充到20个
            padded_matrices = []
            for row in source_matrices:
                new_row = list(row)
                if len(new_row) < 20:
                    new_row.extend([0.0] * (20 - len(new_row)))
                padded_matrices.append(new_row[:20])

            if self.cc_mode:
                converted_matrices = [row[:] for row in padded_matrices]
                status_matrix_index = 0
                cc_to_backend_map = {0: 0, 1: 6, 2: 1, 3: 5, 4: 7, 5: 2, 6: 5}
                cc_statuses = padded_matrices[status_matrix_index]
                backend_statuses = [cc_to_backend_map.get(int(s), int(s)) for s in cc_statuses]
                converted_matrices[status_matrix_index] = backend_statuses
                self.matrices = converted_matrices
            else:
                self.matrices = padded_matrices

        except Exception as e:
            logging.error(f"生成数据时出错: {str(e)}")
        
    def pack_data(self):
        """将数据打包成二进制格式"""
        try:
            data = struct.pack('<' + 'd' * 9, *self.single_values)
            
            for matrix in self.matrices:
                data += struct.pack('<' + 'd' * 20, *matrix)
                
            return data
        except Exception as e:
            logging.error(f"打包数据时出错: {str(e)}")
            return None
        
    def send_data(self):
        """发送数据到服务器"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            logging.info(f"已连接到服务器 {self.host}:{self.port}")
            
            while self.running:
                self.generate_data()
                data = self.pack_data()
                if data:
                    self.socket.send(data)
                    time.sleep(self.delay)
                    
        except ConnectionRefusedError:
            logging.error("连接被拒绝，服务器可能未启动")
        except Exception as e:
            logging.error(f"发送数据时出错: {str(e)}")
        finally:
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
                
    def start(self):
        """启动数据发送"""
        if not self.recorded_data and not self.load_latest_data():
            logging.error("没有可用的记录数据")
            return False
            
        self.running = True
        self.thread = threading.Thread(target=self.send_data)
        self.thread.daemon = True
        self.thread.start()
        logging.info("数据发送已启动")
        return True
        
    def stop(self):
        """停止数据发送"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        logging.info("数据发送已停止")

    def start_recording(self, port=RECORD_PORT):
        """启动录波功能，作为TCP服务器接收Simulink数据"""
        if self.recording:
            logging.warning("录波功能已在运行")
            return False
            
        try:
            cleanup_port(port)
            
            self.record_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.record_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.record_server.bind((TCP_HOST, port))
            self.record_server.listen(1)
            
            self.recording = True
            self.record_data = []
            self.record_start_time = datetime.now()
            
            self.record_thread = threading.Thread(target=self._record_server_loop, args=(port,))
            self.record_thread.daemon = True
            self.record_thread.start()
            
            logging.info(f"录波服务器已启动，监听端口 {port}")
            return True
            
        except Exception as e:
            logging.error(f"启动录波服务器失败: {str(e)}")
            return False
            
    def _record_server_loop(self, port):
        """录波服务器主循环"""
        try:
            while self.recording:
                try:
                    logging.info(f"等待Simulink连接到端口 {port}...")
                    client_socket, addr = self.record_server.accept()
                    logging.info(f"Simulink已连接: {addr}")
                    
                    self._handle_record_client(client_socket)
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.recording:
                        logging.error(f"录波服务器错误: {str(e)}")
                    
        except Exception as e:
            logging.error(f"录波服务器主循环错误: {str(e)}")
        finally:
            if self.record_server:
                try:
                    self.record_server.close()
                except:
                    pass
                    
    def _handle_record_client(self, client_socket):
        """处理录波客户端连接"""
        try:
            client_socket.settimeout(1.0)
            
            while self.recording:
                try:
                    expected_size = 9 * 8 + 5 * 20 * 8
                    data = b''
                    
                    while len(data) < expected_size:
                        chunk = client_socket.recv(expected_size - len(data))
                        if not chunk:
                            logging.warning("客户端断开连接")
                            return
                        data += chunk
                    
                    parsed_data = self._parse_received_data(data)
                    if parsed_data:
                        parsed_data['timestamp'] = datetime.now().isoformat()
                        parsed_data['relative_time'] = (datetime.now() - self.record_start_time).total_seconds()
                        
                        self.record_data.append(parsed_data)
                        
                        if len(self.record_data) % 100 == 0:
                            logging.info(f"已录制 {len(self.record_data)} 条数据")
                            
                except socket.timeout:
                    continue
                except Exception as e:
                    logging.error(f"处理录波数据时出错: {str(e)}")
                    break
                    
        except Exception as e:
            logging.error(f"录波客户端处理错误: {str(e)}")
        finally:
            try:
                client_socket.close()
            except:
                pass
                
    def _parse_received_data(self, data):
        """解析接收到的二进制数据"""
        expected_size = 9 * 8 + 5 * 20 * 8
        try:
            if len(data) != expected_size:
                logging.warning(f"数据长度不正确: {len(data)}, 期望: {expected_size}")
                return None
                
            offset = 0
            
            single_values = []
            for i in range(9):
                value = struct.unpack('<d', data[offset:offset+8])[0]
                single_values.append(value)
                offset += 8
                
            matrices = []
            for i in range(5):
                matrix = []
                for j in range(20):
                    value = struct.unpack('<d', data[offset:offset+8])[0]
                    matrix.append(value)
                    offset += 8
                matrices.append(matrix)
                
            return {
                'single_values': single_values,
                'matrices': matrices
            }
            
        except Exception as e:
            logging.error(f"解析数据时出错: {str(e)}")
            return None
            
    def stop_recording(self):
        """停止录波并保存数据"""
        if not self.recording:
            logging.warning("录波功能未在运行")
            return False
            
        self.recording = False
        
        if self.record_thread:
            self.record_thread.join(timeout=3)
            
        if self.record_server:
            try:
                self.record_server.close()
            except:
                pass
            self.record_server = None
            
        if self.record_data:
            filename = f"recorded_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(self.data_dir, filename)
            
            try:
                with open(filepath, 'w') as f:
                    json.dump(self.record_data, f, indent=2)
                    
                logging.info(f"录波数据已保存: {filepath}, 共 {len(self.record_data)} 条记录")
                return True
                
            except Exception as e:
                logging.error(f"保存录波数据失败: {str(e)}")
                return False
        else:
            logging.warning("没有录制到数据")
            return False

sender = None

def signal_handler(signum, frame):
    """信号处理函数"""
    global sender
    logging.info("收到停止信号，正在清理...")
    if sender:
        sender.stop()
        if sender.recording:
            sender.stop_recording()
    cleanup_port(TCP_PORT)
    cleanup_port(RECORD_PORT)
    sys.exit(0)

def print_usage():
    """打印使用说明"""
    print("\n使用方法:")
    print("  python Simsend3.py send [--speed <n>] [--cc] - 发送模式")
    print("  python Simsend3.py record              - 录波模式：接收Simulink数据并保存")
    print("  python Simsend3.py                     - 默认发送模式")
    print("\n参数:")
    print("  --speed <n>   设置发送频率为每秒 n 次 (默认: 1)")
    print("  --cc          启用CC模式")
    print("\n录波模式说明:")
    print(f"  - 监听端口: {RECORD_PORT}")
    print("  - 数据保存路径: ./data/")
    print("  - 按Ctrl+C停止录波并保存数据")
    print("\n发送模式说明:")
    print(f"  - 连接端口: {TCP_PORT}")
    print("  - 自动加载最新的录制数据文件")
    print("  - 循环发送")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 解析参数
    args = sys.argv[1:]
    speed = 1
    cc_mode = False

    if '--speed' in args:
        try:
            idx = args.index('--speed')
            speed = int(args[idx + 1])
            args.pop(idx + 1)
            args.pop(idx)
        except (ValueError, IndexError):
            print("错误: --speed 参数需要一个有效的整数值。")
            sys.exit(1)

    if '--cc' in args:
        cc_mode = True
        args.remove('--cc')

    mode = "send"
    if len(args) > 0:
        if args[0].lower() in ["record", "录波", "r"]:
            mode = "record"
        elif args[0].lower() in ["send", "发送", "s"]:
            mode = "send"
        elif args[0].lower() in ["help", "h", "-h", "--help"]:
            print_usage()
            sys.exit(0)
        else:
            print(f"未知参数: {args[0]}")
            print_usage()
            sys.exit(1)
    
    try:
        sender = SimSend3(cc_mode=cc_mode, speed=speed)
        
        if cc_mode:
            logging.info("CC模式已激活，将使用新的状态映射。")

        if mode == "record":
            logging.info("启动录波模式...")
            if sender.start_recording():
                logging.info(f"录波服务器运行中，监听端口 {RECORD_PORT}")
                logging.info("等待Simulink连接... 按Ctrl+C停止录波")
                while sender.recording:
                    time.sleep(0.1)
            else:
                logging.error("录波启动失败")
                
        else:
            logging.info("启动发送模式...")
            if sender.start():
                logging.info(f"数据发送运行中，连接端口 {TCP_PORT}, 发送频率: 每秒{speed}次")
                logging.info("按Ctrl+C停止发送...")
                while sender.running:
                    time.sleep(0.1)
            else:
                logging.error("发送启动失败")
                
    except KeyboardInterrupt:
        logging.info("收到中断信号")
    except Exception as e:
        logging.error(f"程序运行出错: {str(e)}")
        traceback.print_exc()
    finally:
        if sender:
            sender.stop()
            if sender.recording:
                sender.stop_recording()
        cleanup_port(TCP_PORT)
        cleanup_port(RECORD_PORT)
