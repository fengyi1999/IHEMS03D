"""
智慧绿氢管理系统启动脚本
用于简化启动过程，提供命令行参数支持
"""
import os
import sys
import argparse
import webbrowser
import time
import subprocess
import signal
import io
import socket
import threading
import http.server
import socketserver

# 设置工作目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 全局变量
frontend_server = None

# 设置日志输出函数
def log_info(message):
    """输出带时间戳的信息日志"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"[INFO] {timestamp} - {message}")

def free_port_if_occupied(port):
    """检查端口是否被占用，如果是，则尝试终止占用该端口的进程 (仅支持Windows)"""
    if not sys.platform.startswith('win'):
        log_info(f"端口检查功能目前仅支持Windows系统。")
        return

    log_info(f"正在检查端口 {port} 是否被占用...")
    try:
        command = f'netstat -aon | findstr "LISTENING" | findstr ":{port}"'
        # 使用GBK编码以正确处理中文Windows环境下的输出
        result = subprocess.run(command, shell=True, capture_output=True, text=True, errors='ignore', encoding='gbk')
        
        if result.stdout:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 4 and parts[-1].isdigit():
                    pid = parts[-1]
                    log_info(f"端口 {port} 被进程 PID: {pid} 占用。正在尝试终止该进程...")
                    kill_command = f"taskkill /F /PID {pid}"
                    kill_result = subprocess.run(kill_command, shell=True, capture_output=True, text=True, errors='ignore')
                    if kill_result.returncode == 0:
                        log_info(f"成功终止进程 PID: {pid}。")
                        time.sleep(1) # 等待端口释放
                    else:
                        log_info(f"警告: 终止进程 PID: {pid} 失败。错误: {kill_result.stderr.strip()}")
        else:
            log_info(f"端口 {port} 未发现被占用。")
            
    except Exception as e:
        log_info(f"检查或释放端口 {port} 时出错: {e}")

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='智慧绿氢管理系统启动脚本')

    parser.add_argument('--no-browser', action='store_true',
                        help='不自动打开浏览器')

    parser.add_argument('--tcp-port', type=int, default=14001,
                        help='TCP服务器端口号，默认为14001')

    parser.add_argument('--ws-port', type=int, default=5002,
                        help='WebSocket服务器端口号，默认为5002')

    parser.add_argument('--no-db', action='store_true',
                        help='不使用数据库，数据将保存在内存中')

    parser.add_argument('--no-save', action='store_true',
                        help='不保存接收到的TCP数据到数据库或缓存')
    
    parser.add_argument('--speed', type=int, default=None,
                        help='仿真速度倍数，不指定则为正常模式')
    
    parser.add_argument('--test', action='store_true',
                        help='启用测试模式，打印更多调试信息')
                        
    parser.add_argument('--min', type=int, default=None,
                        help='数据聚合分钟数，例如15表示将1分钟数据点聚合为15分钟数据点')
    
    return parser.parse_args()

def update_config(args):
    """根据命令行参数更新配置文件"""
    import re
    import importlib
    config_path = os.path.join(BASE_DIR, 'backend', 'config.py')

    log_info(f"正在更新配置文件: {config_path}")

    # 读取配置文件
    with open(config_path, 'r', encoding='utf-8') as f:
        config_content = f.read()

    # 使用正则表达式更新TCP端口
    config_content = re.sub(
        r'TCP_PORT\s*=\s*\d+',
        f'TCP_PORT = {args.tcp_port}',
        config_content
    )

    # 确保模拟数据模式为False，启用TCP服务器
    config_content = re.sub(
        r'SIMULATE_DATA\s*=\s*(True|False)',
        'SIMULATE_DATA = False',
        config_content
    )
    log_info("已禁用模拟数据模式，将启动TCP服务器")

    # 更新数据库配置
    if args.no_db:
        config_content = re.sub(
            r'NO_DB\s*=\s*(True|False)',
            'NO_DB = True',
            config_content
        )
        log_info("已启用无数据库模式")

    # 更新数据保存配置
    if args.no_save:
        config_content = re.sub(
            r'SAVE_DATA\s*=\s*(True|False)',
            'SAVE_DATA = False',
            config_content
        )
        log_info("已禁用数据保存")

    # 更新仿真速度配置
    if args.speed is not None:
        config_content = re.sub(
            r'SPEED\s*=\s*\d+',
            f'SPEED = {args.speed}',
            config_content
        )
        log_info(f"已设置仿真速度倍数为: {args.speed}")
    else:
        # 正常模式，设置速度为1
        config_content = re.sub(
            r'SPEED\s*=\s*\d+',
            'SPEED = 1',
            config_content
        )
        log_info("正常模式: 数据接收频率为每秒1次")

    # 更新数据聚合分钟数
    aggregation_minutes_val = args.min if args.min is not None else 1
    aggregation_minutes_str = f"AGGREGATION_MINUTES = {aggregation_minutes_val}"
    if re.search(r'AGGREGATION_MINUTES\s*=', config_content):
        config_content = re.sub(
            r'AGGREGATION_MINUTES\s*=\s*.*',
            aggregation_minutes_str,
            config_content
        )
    else:
        config_content += f'\n{aggregation_minutes_str}\n'
    
    if args.min is not None:
        log_info(f"已设置数据聚合分钟数为: {args.min}")
    else:
        log_info("默认数据聚合模式: 1分钟 (不聚合)")

    # 写回配置文件
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(config_content)

    # 重新加载配置模块
    log_info("正在重新加载配置模块")
    import backend.config
    importlib.reload(backend.config)

    # 打印确认信息
    log_info(f"配置已更新: TCP端口={args.tcp_port}")
    log_info(f"当前实际配置的TCP端口: {backend.config.TCP_PORT}")
    log_info(f"模拟数据模式: {backend.config.SIMULATE_DATA}")
    log_info(f"无数据库模式: {backend.config.NO_DB}")
    log_info(f"数据保存: {backend.config.SAVE_DATA}")

def start_backend_server(args):
    """启动后端服务器"""
    log_info("正在启动后端服务器...")

    # 检查后端文件是否存在
    backend_path = os.path.join(BASE_DIR, 'backend', 'app.py')
    if not os.path.exists(backend_path):
        log_info(f"错误: 后端文件不存在: {backend_path}")
        return None

    log_info(f"后端文件路径: {backend_path}")

    # 创建新的进程组
    kwargs = {}
    if not sys.platform.startswith('win'):
        kwargs['preexec_fn'] = os.setsid

    # 启动后端进程
    log_info(f"使用Python解释器: {sys.executable}")
    log_info("正在执行: python backend/app.py")

    # 启动后端进程，并传递test参数
    command = [sys.executable, 'backend/app.py']
    if args.test:
        command.append('--test') # 将--test标志传递给app.py
    
    backend_process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=False,  # 使用二进制模式，以便正确处理中文
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
        **kwargs
    )

    # 等待一段时间，检查进程是否正常启动
    time.sleep(1)
    if backend_process.poll() is not None:
        log_info(f"错误: 后端进程启动失败，退出码: {backend_process.poll()}")
        # 尝试读取错误输出
        try:
            output_bytes, _ = backend_process.communicate()
            # 尝试多种编码解码
            for encoding in ['utf-8', 'gbk', 'latin-1']:
                try:
                    output = output_bytes.decode(encoding)
                    log_info(f"后端进程输出: {output}")
                    break
                except UnicodeDecodeError:
                    continue
            else:
                # 如果所有编码都失败，使用latin-1（它不会失败，但可能显示乱码）
                output = output_bytes.decode('latin-1')
                log_info(f"后端进程输出(可能乱码): {output}")
        except Exception as e:
            log_info(f"读取后端进程输出时出错: {e}")
        return None

    log_info("后端服务器已启动，进程ID: " + str(backend_process.pid))

    # 启动一个线程来读取后端输出
    def read_output(process):
        while process.poll() is None:
            try:
                # 使用二进制模式读取
                line_bytes = process.stdout.readline()
                if line_bytes:
                    try:
                        # 首先尝试UTF-8解码
                        line = line_bytes.decode('utf-8').strip()
                        if line:
                            print(f"[后端] {line}")
                    except UnicodeDecodeError:
                        try:
                            # 如果UTF-8失败，尝试GBK解码（中文Windows常用）
                            line = line_bytes.decode('gbk').strip()
                            if line:
                                print(f"[后端] {line}")
                        except UnicodeDecodeError:
                            # 如果GBK也失败，使用latin-1（它不会失败，但可能显示乱码）
                            line = line_bytes.decode('latin-1').strip()
                            if line:
                                print(f"[后端-二进制] {line}")
            except Exception as e:
                print(f"[读取后端输出错误] {str(e)}")
                time.sleep(0.1)

    threading.Thread(target=read_output, args=(backend_process,), daemon=True).start()

    return backend_process

def open_frontend(args):
    """打开前端界面"""
    global frontend_server
    
    if not args.no_browser:
        # 使用Vue 2前端
        frontend_path = os.path.join(BASE_DIR, 'frontend', 'index.html')
        frontend_type = "Vue 2"
        frontend_url = f'file://{os.path.abspath(frontend_path)}'

        # 检查前端文件是否存在
        if not os.path.exists(frontend_path):
            log_info(f"错误: 前端文件不存在: {frontend_path}")
            return False

        log_info(f"前端类型: {frontend_type}")
        log_info(f"前端文件路径: {frontend_path}")

        # 检查WebSocket服务器是否可以连接，并等待其启动
        log_info("正在检查WebSocket服务器连接...")
        ws_port = args.ws_port
        port_opened = False
        for i in range(5): # 尝试5次，总共等待5秒
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(0.5) # 缩短超时
                    result = sock.connect_ex(('127.0.0.1', ws_port))
                    if result == 0:
                        log_info(f"WebSocket服务器端口 {ws_port} 已开放。")
                        port_opened = True
                        break
            except Exception as e:
                log_info(f"检查WebSocket服务器时出错: {e}")
            
            if not port_opened:
                time.sleep(1)

        if not port_opened:
            log_info(f"警告: WebSocket服务器端口 {ws_port} 在5秒后仍未开放，前端可能无法连接。")

        # 检查前端配置文件
        config_js_path = os.path.join(BASE_DIR, 'frontend', 'js', 'config.js')
        if os.path.exists(config_js_path):
            try:
                with open(config_js_path, 'r', encoding='utf-8') as f:
                    config_content = f.read()
                    log_info(f"前端配置文件内容: {config_content[:200]}...")
            except Exception as e:
                log_info(f"读取前端配置文件时出错: {e}")
        else:
            log_info(f"警告: 前端配置文件不存在: {config_js_path}")

        # 延迟1秒，确保后端已启动
        log_info("等待1秒，确保后端服务已完全启动...")
        time.sleep(1)

        # 打开浏览器
        log_info(f"正在打开前端界面: {frontend_url}")
        try:
            browser_opened = webbrowser.open(frontend_url)
            if browser_opened:
                log_info("浏览器已成功打开")
            else:
                log_info("警告: 浏览器打开失败")
        except Exception as e:
            log_info(f"打开浏览器时出错: {e}")

        return True
    else:
        log_info("已设置不自动打开浏览器")
        return False

def cleanup_process(process):
    """清理进程"""
    global frontend_server
    
    # 先清理前端HTTP服务器
    if frontend_server:
        log_info("正在关闭前端HTTP服务器...")
        try:
            frontend_server.shutdown()
            frontend_server.server_close()
            log_info("前端HTTP服务器已关闭")
        except Exception as e:
            log_info(f"关闭前端HTTP服务器时出错: {e}")
        finally:
            frontend_server = None
    
    if not process:
        log_info("没有需要清理的后端进程")
        return 0

    log_info(f"正在清理进程 (PID: {process.pid})...")

    try:
        if sys.platform.startswith('win'):
            # Windows下使用taskkill强制终止进程树
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)],
                          stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        else:
            # Linux/Mac下发送SIGTERM信号
            process.terminate()

        # 等待进程终止
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        # 如果进程在5秒内没有响应，强制杀死
        process.kill()
        process.wait()  # 等待进程完全终止
    except Exception as e:
        log_info(f'停止服务时出错: {e}')
        return 1

    log_info("进程清理完成")
    return 0

def main():
    """主函数"""
    log_info("=== 智慧绿氢管理系统启动 ===")
    log_info(f"工作目录: {BASE_DIR}")

    # 解析命令行参数
    log_info("正在解析命令行参数...")
    args = parse_arguments()
    log_info(f"命令行参数: {args}")

    # 检查并释放可能被占用的端口
    free_port_if_occupied(args.ws_port)
    free_port_if_occupied(args.tcp_port)

    # 更新配置文件
    update_config(args)

    backend_process = None

    try:
        # 启动后端服务
        backend_process = start_backend_server(args)
        if not backend_process:
            log_info("后端服务启动失败，程序终止")
            return 1

        # 检查后端服务是否正常运行
        time.sleep(2)
        if backend_process.poll() is not None:
            log_info(f"后端服务异常退出，退出码: {backend_process.poll()}")
            return 1

        # 打开前端界面
        log_info("正在打开前端界面...")
        frontend_result = open_frontend(args)
        if not frontend_result and not args.no_browser:
            log_info("前端界面打开失败")

        # 等待用户终止
        log_info("系统已启动，按Ctrl+C终止...")
        while True:
            if backend_process.poll() is not None:
                log_info(f"后端服务已终止，退出码: {backend_process.poll()}")
                return 1
            time.sleep(1)

    except KeyboardInterrupt:
        log_info("\n收到终止信号，正在关闭服务...")
        return cleanup_process(backend_process)
    except Exception as e:
        log_info(f"启动过程中出错: {e}")
        import traceback
        log_info(traceback.format_exc())
        return 1
    finally:
        if backend_process and backend_process.poll() is None:
            cleanup_process(backend_process)

    log_info("=== 智慧绿氢管理系统已关闭 ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())
