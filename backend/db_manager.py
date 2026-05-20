"""
数据库管理器 - 处理数据的存储和检索
支持与SQLite数据库交互，以及数据归档和统计分析
"""
import sqlite3
import time
import json
import logging
import os
import threading
from datetime import datetime, timedelta, time as dt_time

# 使用相对导入来解决模块导入问题
try:
    import config
except ImportError:
    # 如果直接导入失败，尝试从backend包中导入
    try:
        from backend import config
    except ImportError:
        # 如果仍然失败，尝试从当前目录或上级目录导入
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import config

# 创建日志器
logger = logging.getLogger('db_manager')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class DatabaseManager:
    """
    数据库管理器类，处理与SQLite数据库的交互
    当数据库不可用时，将在内存中缓存数据
    支持数据归档、统计分析和数据清理
    """
    def __init__(self):
        """初始化数据库管理器"""
        self.connection = None
        self.connected = False
        self.no_db_mode = False
        self.db_file = None

        # 内存缓存，用于无数据库模式
        self.memory_data = []

        # 线程锁，用于保护内存数据的读写和数据库连接
        self.memory_lock = threading.Lock()
        self.db_lock = threading.Lock()

        # 归档任务计划
        self.archive_task = None
        self.archive_running = False

    def connect(self):
        """连接到SQLite数据库并初始化数据表"""
        # 检查是否指定了无数据库模式
        if getattr(config, 'NO_DB', False):
            self.no_db_mode = True
            logger.info("已开启无数据库模式，数据将保存在内存中")
            print("已开启无数据库模式，数据将保存在内存中")
            # 启动定时内存清理任务
            self._start_memory_cleanup_task()
            return True

        # 尝试连接数据库
        try:
            # 确保数据目录存在
            db_file = getattr(config, 'DB_FILE', 'data/ems_db.sqlite')
            db_dir = os.path.dirname(os.path.abspath(db_file))

            if not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"创建数据库目录: {db_dir}")

            # 保存数据库文件路径
            self.db_file = db_file

            # 使用线程锁保护连接操作
            with self.db_lock:
                # 连接到SQLite数据库（如果不存在将自动创建）
                self.connection = sqlite3.connect(db_file, check_same_thread=False)

                # 启用外键支持
                self.connection.execute("PRAGMA foreign_keys = ON")

                # 让SQLite返回行作为字典，便于后续处理
                self.connection.row_factory = sqlite3.Row

                # 启用WAL模式提高并发性和写入性能
                self.connection.execute("PRAGMA journal_mode = WAL")

                # 创建数据表
                cursor = self.connection.cursor()
                self._create_tables(cursor)
                self.connection.commit()
                cursor.close()

            self.connected = True

            # 启动定时归档任务
            self._start_archive_task()

            logger.info(f"已连接到SQLite数据库: {db_file}")
            print(f"已连接到SQLite数据库: {db_file}")
            return True

        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            print(f"数据库连接失败: {e}")
            # 如果连接失败，切换到无数据库模式
            self.no_db_mode = True
            logger.warning("已自动切换到无数据库模式，数据将保存在内存中")
            print("已自动切换到无数据库模式，数据将保存在内存中")
            # 启动定时内存清理任务
            self._start_memory_cleanup_task()
            return True  # 即使数据库连接失败，也返回true，允许系统继续运行

    def _create_tables(self, cursor):
        """创建必要的数据表，包含实时数据、历史数据和统计数据表"""
        # 创建实时数据表 - 存储最近一段时间的原始数据
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS realtime_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            data_json TEXT NOT NULL,
            source TEXT DEFAULT 'tcp',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 创建实时数据表的索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_realtime_timestamp ON realtime_data(timestamp)")

        # 创建历史数据表 - 存储历史分小时数据
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS historical_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_hour DATETIME NOT NULL,
            data_json TEXT NOT NULL,
            record_count INTEGER NOT NULL,
            min_timestamp INTEGER NOT NULL,
            max_timestamp INTEGER NOT NULL,
            compressed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (date_hour)
        )
        """)

        # 创建小时统计数据表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS hourly_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_hour DATETIME NOT NULL,
            avg_power REAL,
            max_power REAL,
            min_power REAL,
            power_variance REAL,
            total_production REAL,
            total_consumption REAL,
            wind_power_avg REAL,
            solar_power_avg REAL,
            grid_power_avg REAL,
            hydrogen_power_avg REAL,
            stats_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (date_hour)
        )
        """)

        # 创建日统计数据表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE NOT NULL,
            avg_power REAL,
            max_power REAL,
            min_power REAL,
            power_variance REAL,
            total_production REAL,
            total_consumption REAL,
            wind_power_avg REAL,
            solar_power_avg REAL,
            grid_power_avg REAL,
            hydrogen_power_avg REAL,
            data_points INTEGER,
            stats_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (date)
        )
        """)

        # 创建系统日志表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            log_level TEXT NOT NULL,
            component TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 创建系统日志表的索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON system_logs(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_component ON system_logs(component)")

        logger.info("数据表创建完成")

    def save_data(self, data):
        """
        保存实时数据到数据库或内存

        参数:
            data: 实时数据，包含timestamp和data字段

        返回:
            成功返回True，失败返回False
        """
        # 检查配置是否且条件是否允许保存数据
        if not getattr(config, 'SAVE_DATA', True):
            logger.debug("根据配置，不保存数据")
            return True

        # 无数据库模式下，保存到内存
        if self.no_db_mode:
            try:
                # 使用线程锁保护内存数据访问
                with self.memory_lock:
                    self.memory_data.append(data.copy())
                return {'success': True, 'mode': 'memory', 'message': '数据已保存到内存'}
            except Exception as e:
                logger.error(f"内存模式下保存数据失败: {e}")
                return {'success': False, 'mode': 'memory', 'message': f'保存失败: {e}'}

        # 数据库模式
        try:
            # 准备JSON数据
            data_json = json.dumps(data)

            # 使用线程锁保护数据库访问
            with self.db_lock:
                # 插入数据（使用问号占位符而不是%s）
                cursor = self.connection.cursor()
                cursor.execute(
                    "INSERT INTO realtime_data (timestamp, data_json, source) VALUES (?, ?, ?)",
                    (data['timestamp'], data_json, data.get('source', 'tcp'))
                )

                # 提交事务
                self.connection.commit()
                cursor.close()

            # 检查是否需要触发归档或统计操作
            now = datetime.fromtimestamp(data['timestamp'])

            # 如果是某一小时的后55分钟，将触发小时统计
            if now.minute >= 55 and now.second >= 50:
                # 获取当前小时的起始时间
                hour_start = now.replace(minute=0, second=0, microsecond=0)
                # 异步计算当前小时的统计数据
                threading.Thread(target=self._generate_hourly_stats, args=(hour_start,), daemon=True).start()

            # 如果是一天结束时，触发每日统计
            if now.hour == 23 and now.minute >= 55 and now.second >= 50:
                # 获取当天日期
                current_date = now.date()
                # 异步计算每日统计
                threading.Thread(target=self._generate_daily_stats, args=(current_date,), daemon=True).start()

            return {'success': True, 'mode': 'database', 'message': '数据已保存到SQLite数据库'}

        except Exception as e:
            logger.error(f"数据库保存数据失败: {e}")
            # 只在非speed模式下输出错误信息
            import config
            if not hasattr(config, 'SPEED') or config.SPEED <= 1:
                print(f"保存数据失败: {e}")

            # 尝试切换到内存模式
            self.no_db_mode = True
            logger.warning("切换到内存模式尝试保存数据")
            if not hasattr(config, 'SPEED') or config.SPEED <= 1:
                print("正在尝试将数据保存到内存...")

            try:
                with self.memory_lock:
                    self.memory_data.append(data.copy())
                return {'success': True, 'mode': 'memory', 'message': f'数据库写入失败: {e}，数据已保存到内存'}
            except Exception as mem_error:
                logger.error(f"内存备份保存也失败: {mem_error}")
                return {'success': False, 'mode': 'none', 'message': '保存完全失败'}

    def get_recent_data(self, limit=60, source=None):
        """
        获取最近的实时数据

        参数:
            limit: 获取的数据条数上限
            source: 可选的数据源过滤，例如'tcp'或'simulator'

        返回:
            数据列表，如果失败则返回空列表
        """
        # 无数据库模式 - 从内存中获取
        if self.no_db_mode:
            try:
                with self.memory_lock:  # 使用线程锁保护共享数据
                    # 过滤数据源（如果指定）
                    if source:
                        filtered_data = [d for d in self.memory_data if d.get('source', 'tcp') == source]
                    else:
                        filtered_data = self.memory_data.copy()

                    # 按时间戳排序
                    sorted_data = sorted(filtered_data, key=lambda x: x['timestamp'])

                    # 返回最近的limit条数据
                    return sorted_data[-limit:] if limit < len(sorted_data) else sorted_data
            except Exception as e:
                logger.error(f"从内存获取数据失败: {e}")
                return []

        # 数据库模式
        if not self.connected:
            logger.warning("数据库未连接，无法获取数据")
            return []

        try:
            with self.connection.cursor() as cursor:
                # 准备SQL，根据是否需要过滤数据源
                if source:
                    sql = """
                    SELECT timestamp, data_json, source
                    FROM realtime_data
                    WHERE source = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                    """
                    cursor.execute(sql, (source, limit))
                else:
                    sql = """
                    SELECT timestamp, data_json, source
                    FROM realtime_data
                    ORDER BY timestamp DESC
                    LIMIT %s
                    """
                    cursor.execute(sql, (limit,))

                # 获取结果
                results = cursor.fetchall()

                # 处理结果
                data_list = []
                for row in results:
                    if len(row) >= 3:
                        timestamp, data_json, src = row
                        data_list.append({
                            'timestamp': timestamp,
                            'data': json.loads(data_json),
                            'source': src
                        })
                    else:
                        timestamp, data_json = row[:2]
                        data_list.append({
                            'timestamp': timestamp,
                            'data': json.loads(data_json)
                        })

                # 按时间顺序排序
                data_list.sort(key=lambda x: x['timestamp'])

                return data_list

        except Exception as e:
            logger.error(f"获取最近数据失败: {e}")
            print(f"获取最近数据失败: {e}")
            return []

    def _start_archive_task(self):
        """启动定时归档任务"""
        if self.archive_running:
            return

        def archive_worker():
            self.archive_running = True
            logger.info("数据归档任务启动")

            try:
                while self.connected and not self.no_db_mode:
                    # 执行数据归档
                    self._archive_old_data()

                    # 执行数据清理
                    self._cleanup_realtime_data()

                    # 等待一小时再次执行
                    archive_interval = getattr(config, 'DB_ARCHIVE_INTERVAL_HOURS', 1) * 3600
                    time.sleep(archive_interval)
            except Exception as e:
                logger.error(f"归档任务出错: {e}")
            finally:
                self.archive_running = False
                logger.info("数据归档任务已停止")

        # 启动归档线程
        self.archive_task = threading.Thread(target=archive_worker, daemon=True)
        self.archive_task.start()

    def _start_memory_cleanup_task(self):
        """启动内存数据清理任务"""
        def cleanup_worker():
            logger.info("内存数据清理任务启动")

            try:
                while self.no_db_mode:
                    # 每小时清理一次内存数据
                    with self.memory_lock:
                        # 计算需要保留的数据量
                        now = int(time.time())
                        retention_seconds = getattr(config, 'DB_REALTIME_RETENTION_DAYS', 2) * 86400
                        cutoff_time = now - retention_seconds

                        # 只保留指定时间范围内的数据
                        old_count = len(self.memory_data)
                        self.memory_data = [d for d in self.memory_data if d['timestamp'] >= cutoff_time]
                        new_count = len(self.memory_data)

                        if old_count > new_count:
                            logger.info(f"内存数据清理完成，删除了 {old_count - new_count} 条数据，当前数据量: {new_count}")

                    # 等待一小时
                    time.sleep(3600)
            except Exception as e:
                logger.error(f"内存数据清理任务出错: {e}")

        # 启动内存清理线程
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()

    def _check_memory_stats(self, current_timestamp):
        """检查并触发内存数据统计"""
        # 简化版本，只保留基本功能
        if not self.no_db_mode:
            return

    def _archive_old_data(self):
        """将旧的实时数据归档到历史数据表"""
        if self.no_db_mode:
            logger.debug("无数据库模式，跳过归档操作")
            return

        if not self.connected:
            logger.warning("数据库未连接，无法归档数据")
            return

        try:
            # 获取当前时间和归档间隔
            now = datetime.now()
            archive_interval = getattr(config, 'DB_ARCHIVE_INTERVAL_HOURS', 1)  # 默认1小时

            # 计算要归档的时间范围（按小时分组）
            archive_before = now - timedelta(hours=1)  # 归档一小时以前的数据
            archive_hour = archive_before.replace(minute=0, second=0, microsecond=0)

            # 使用线程锁保护数据库访问
            with self.db_lock:
                # 检查该小时的数据是否已经归档
                cursor = self.connection.cursor()
                cursor.execute("SELECT COUNT(*) FROM historical_data WHERE date_hour = ?", (archive_hour.strftime('%Y-%m-%d %H:%M:%S'),))

                # SQLite使用索引0获取第一列数据
                if cursor.fetchone()[0] > 0:
                    logger.debug(f"{archive_hour}的数据已经归档，跳过")
                    cursor.close()
                    return

                # 获取该小时范围的数据
                start_timestamp = int(archive_hour.timestamp())
                end_timestamp = int((archive_hour + timedelta(hours=1)).timestamp())

                cursor.execute(
                    "SELECT data_json FROM realtime_data WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp",
                    (start_timestamp, end_timestamp)
                )

                rows = cursor.fetchall()
                if not rows:
                    logger.debug(f"{archive_hour}没有数据需要归档")
                    cursor.close()
                    return

                # 将该小时的数据进行合并归档
                data_list = [json.loads(row[0]) for row in rows]
                min_timestamp = min(d.get('timestamp', start_timestamp) for d in data_list)
                max_timestamp = max(d.get('timestamp', end_timestamp-1) for d in data_list)

                # 将合并后的数据保存到历史表
                data_json = json.dumps(data_list)

                # 使用SQLite参数占位符
                cursor.execute(
                    """
                    INSERT INTO historical_data
                    (date_hour, data_json, record_count, min_timestamp, max_timestamp, compressed)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (archive_hour.strftime('%Y-%m-%d %H:%M:%S'), data_json, len(data_list), min_timestamp, max_timestamp, 0)
                )

                # 清理已归档的实时数据
                cursor.execute(
                    "DELETE FROM realtime_data WHERE timestamp >= ? AND timestamp < ?",
                    (start_timestamp, end_timestamp)
                )

                deleted_count = cursor.rowcount

                # 生成该小时的统计数据
                self._generate_hourly_stats(archive_hour)

                # 提交事务
                self.connection.commit()
                cursor.close()

                # 记录归档信息
                logger.info(f"归档完成: {archive_hour}, 共 {len(data_list)} 条数据, 清理 {deleted_count} 条实时数据")

        except Exception as e:
            logger.error(f"数据归档失败: {e}")
            print(f"数据归档失败: {e}")

    def _cleanup_realtime_data(self):
        """清理过旧的实时数据"""
        if self.no_db_mode:
            # 在内存模式下清理内存数据
            try:
                with self.memory_lock:
                    if not self.memory_data:
                        return

                    # 保留过去48小时的数据
                    retention_time = int(time.time()) - 48 * 3600
                    original_count = len(self.memory_data)

                    # 过滤掉旧数据
                    self.memory_data = [d for d in self.memory_data if d.get('timestamp', 0) >= retention_time]

                    cleaned_count = original_count - len(self.memory_data)
                    if cleaned_count > 0:
                        logger.info(f"内存模式: 清理了 {cleaned_count} 条过时数据")
            except Exception as e:
                logger.error(f"内存数据清理失败: {e}")
            return

        # 数据库模式清理数据
        if not self.connected:
            return

        try:
            # 获取数据保留天数
            retention_days = getattr(config, 'DB_REALTIME_RETENTION_DAYS', 2)
            cutoff_time = int((datetime.now() - timedelta(days=retention_days)).timestamp())

            # 使用线程锁保护数据库访问
            with self.db_lock:
                # 删除旧数据
                cursor = self.connection.cursor()
                cursor.execute("DELETE FROM realtime_data WHERE timestamp < ?", (cutoff_time,))
                deleted_count = cursor.rowcount

                # 提交事务
                self.connection.commit()
                cursor.close()

                if deleted_count > 0:
                    logger.info(f"已清理 {deleted_count} 条过时的实时数据")
                    print(f"已清理 {deleted_count} 条过时的实时数据")

            # VACUUM操作必须在事务外执行
            try:
                # 单独执行VACUUM
                cursor = self.connection.cursor()
                cursor.execute("VACUUM")
                cursor.close()
                logger.debug("VACUUM操作成功执行")
            except Exception as vacuum_err:
                logger.warning(f"VACUUM操作失败: {vacuum_err}")

        except Exception as e:
            logger.error(f"清理实时数据失败: {e}")
            print(f"清理实时数据失败: {e}")

    def calculate_daily_stats(self, date=None):
        """
        计算指定日期的统计数据

        参数:
            date: 日期字符串，格式为'YYYY-MM-DD'，如果为None则使用今天

        返回:
            统计数据字典，如果失败则返回None
        """
        # 转换date为date对象
        if date is None:
            target_date = datetime.now().date()
        elif isinstance(date, str):
            try:
                target_date = datetime.strptime(date, '%Y-%m-%d').date()
            except ValueError:
                logger.error(f"日期格式无效: {date}")
                return None
        else:
            target_date = date

        # 如果在无数据库模式下，从内存中计算
        if self.no_db_mode:
            try:
                day_start = int(datetime.combine(target_date, dt_time.min).timestamp())
                day_end = int(datetime.combine(target_date, dt_time.max).timestamp())

                with self.memory_lock:
                    # 筛选目标日期的数据
                    day_data = [d for d in self.memory_data
                              if d['timestamp'] >= day_start and d['timestamp'] <= day_end]

                    if not day_data:
                        return None

                    return self._calculate_power_stats(day_data)
            except Exception as e:
                logger.error(f"计算内存每日统计失败: {e}")
                return None

        # 数据库模式
        if not self.connected:
            return None

        try:
            # 使用线程锁保护数据库访问
            with self.db_lock:
                # 格式化日期字符串用于 SQLite
                target_date_str = target_date.strftime('%Y-%m-%d')

                # 尝试从统计表中获取
                cursor = self.connection.cursor()
                cursor.execute("""
                    SELECT stats_json
                    FROM daily_stats
                    WHERE date = ?
                """, (target_date_str,))

                result = cursor.fetchone()
                cursor.close()

                if result:
                    return json.loads(result[0])

                # 如果统计不存在，计算并生成
                return self._generate_daily_stats(target_date)

        except Exception as e:
            logger.error(f"计算每日统计失败: {e}")
            return None

    def _generate_hourly_stats(self, hour_start):
        """生成指定小时的统计数据（占位符）"""
        # TODO: 实现小时统计逻辑
        logger.debug(f"触发小时统计计算: {hour_start} (占位符)")
        pass

    def _generate_daily_stats(self, target_date):
        """生成指定日期的统计数据（占位符）"""
        # TODO: 实现每日统计逻辑
        logger.debug(f"触发每日统计计算: {target_date} (占位符)")
        # 示例：可以调用 _calculate_power_stats 并保存结果
        # stats = self._calculate_power_stats_for_day(target_date)
        # if stats:
        #     # 保存到 daily_stats 表
        #     pass
        return None # 返回None表示未实际生成或保存

    def save_data(self, data):
        """
        将数据保存到SQLite数据库或内存中

        参数:
            data: 要保存的数据字典，包含timestamp和其他数据项

        返回:
            字典，包含操作结果信息
        """
        # 确保数据有时间戳
        if 'timestamp' not in data:
            data['timestamp'] = int(time.time())

        # 如果是无数据库模式，直接保存到内存
        if self.no_db_mode:
            try:
                with self.memory_lock:
                    self.memory_data.append(data.copy())

                    # 限制内存中的数据量，避免内存溢出
                    max_records = 3600  # 大约一小时的数据（以每秒一条计算）
                    if len(self.memory_data) > max_records:
                        # 只保留最新的数据
                        self.memory_data = self.memory_data[-max_records:]

                # 触发内存数据统计
                self._check_memory_stats(data['timestamp'])

                return {'success': True, 'mode': 'memory', 'message': '数据已保存到内存'}
            except Exception as e:
                logger.error(f"内存模式下保存数据失败: {e}")
                return {'success': False, 'mode': 'memory', 'message': f'保存失败: {e}'}

        # 数据库模式
        try:
            # 检查连接是否有效
            if not self.connection or not self.connected:
                # 尝试重新连接
                if not self.connect():
                    # 如果重连失败，切换到内存模式
                    with self.memory_lock:
                        self.memory_data.append(data.copy())
                    return {'success': True, 'mode': 'memory', 'message': '数据库连接失效，数据已保存到内存'}

            # 准备JSON数据
            data_json = json.dumps(data)

            # 使用线程锁保护数据库访问
            with self.db_lock:
                # 插入数据（使用问号占位符而不是%s）
                cursor = self.connection.cursor()
                cursor.execute(
                    "INSERT INTO realtime_data (timestamp, data_json, source) VALUES (?, ?, ?)",
                    (data['timestamp'], data_json, data.get('source', 'tcp'))
                )

                # 提交事务
                self.connection.commit()
                cursor.close()

            # 检查是否需要触发归档或统计操作
            now = datetime.fromtimestamp(data['timestamp'])

            # 如果是某一小时的后55分钟，将触发小时统计
            if now.minute >= 55 and now.second >= 50:
                # 获取当前小时的起始时间
                hour_start = now.replace(minute=0, second=0, microsecond=0)
                # 异步计算当前小时的统计数据
                threading.Thread(target=self._generate_hourly_stats, args=(hour_start,), daemon=True).start()

            # 如果是一天结束时，触发每日统计
            if now.hour == 23 and now.minute >= 55 and now.second >= 50:
                # 获取当天日期
                today = now.date()
                # 异步计算当天的统计数据
                threading.Thread(target=self._generate_daily_stats, args=(today,), daemon=True).start()

            return {'success': True, 'mode': 'database', 'message': '数据已保存到SQLite数据库'}

        except Exception as e:
            logger.error(f"数据库保存失败: {e}")
            # 如果数据库操作失败，作为后备存储到内存
            try:
                with self.memory_lock:
                    self.memory_data.append(data.copy())
                return {'success': True, 'mode': 'memory', 'message': f'数据库写入失败: {e}，数据已保存到内存'}
            except Exception as mem_error:
                logger.error(f"内存备份保存也失败: {mem_error}")
                return {'success': False, 'mode': 'none', 'message': '保存完全失败'}

    def get_recent_data(self, limit=100, offset=0):
        """
        获取最近的数据

        参数:
            limit: 返回的最大记录数
            offset: 跳过的记录数

        返回:
            列表，包含最近的数据记录
        """
        # 内存模式下从内存获取
        if self.no_db_mode:
            with self.memory_lock:
                # 按时间戳排序后返回指定范围的数据
                sorted_data = sorted(self.memory_data, key=lambda x: x['timestamp'], reverse=True)
                return sorted_data[offset:offset+limit]

        # 数据库模式
        if not self.connected:
            logger.warning("数据库未连接，无法获取数据")
            return []

        try:
            with self.db_lock:
                cursor = self.connection.cursor()
                cursor.execute(
                    "SELECT timestamp, data_json, source FROM realtime_data ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                    (limit, offset)
                )

                results = cursor.fetchall()
                cursor.close()

            # 处理结果
            data_list = []
            for row in results:
                data = json.loads(row[1])  # 解析JSON数据
                if isinstance(data, dict) and 'timestamp' not in data:
                    data['timestamp'] = row[0]  # 添加时间戳
                data_list.append(data)

            return data_list

        except Exception as e:
            logger.error(f"获取最近数据失败: {e}")
            return []

    def disconnect(self):
        """断开数据库连接"""
        if self.connection:
            self.connection.close()
            self.connected = False
            print("已断开数据库连接")
  