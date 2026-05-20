"""
配置文件 - 存储系统配置参数
"""
# TCP服务器配置
TCP_HOST = '127.0.0.1'  # 本地主机
TCP_PORT = 14001  # TCP服务器端口，修改为14001避免与MySQL冲突

# WebSocket服务器配置
WS_HOST = '0.0.0.0' # 绑定到所有网络接口，支持局域网访问
WS_PORT = 5002  # WebSocket服务器端口

# 数据库配置 - SQLite
DB_FILE = 'data/ems_db.sqlite'  # SQLite数据库文件路径（相对于项目根目录）
NO_DB = False  # 如果设置为True，将不使用数据库，数据只保存在内存中

# 数据存储配置
DB_REALTIME_RETENTION_DAYS = 2  # 实时数据保留天数
DB_ARCHIVE_INTERVAL_HOURS = 1  # 归档间隔（小时）
DB_DAILY_STATS_ENABLED = True  # 是否启用每日统计

# 模拟数据配置
SIMULATE_DATA = False  # 是否使用模拟数据
SIMULATE_INTERVAL = 1  # 模拟数据生成间隔(秒)
SPEED = 1  # 仿真速度倍数，默认为1

# 数据保存配置
SAVE_DATA = True  # 是否将接收到的数据保存到数据库或缓存

# 变量名称配置 - 对应Simulink模型输出的20个变量
VARIABLE_NAMES = [
    'power', 'voltage', 'current', 'frequency', 
    'active_power', 'reactive_power', 'power_factor', 'temperature',
    'humidity', 'pressure', 'flow_rate', 'efficiency',
    'soc', 'carbon_reduction', 'energy_saved', 'production',
    'consumption', 'grid_load', 'battery_voltage', 'battery_current'
]

AGGREGATION_MINUTES = 1
