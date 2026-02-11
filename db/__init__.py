# 数据库连接池模块
import sqlite3
import threading

class DatabasePool:
    def __init__(self, db_name="identifier.sqlite", max_connections=15):
        self.db_name = db_name
        self.max_connections = max_connections
        self.connections = []
        self.lock = threading.Lock()
        
        # 初始化连接池
        for _ in range(min(3, max_connections)):
            self.connections.append(self._create_connection())
    
    def _create_connection(self):
        return sqlite3.connect(self.db_name, check_same_thread=False)
    
    def _is_connection_alive(self, conn):
        """检测数据库连接是否存活"""
        try:
            # 执行一个简单的SQL语句来检测连接是否存活
            conn.execute("SELECT 1")
            return True
        except Exception:
            return False
    
    def get_connection(self):
        with self.lock:
            while self.connections:
                conn = self.connections.pop()
                # 检测连接是否存活
                if self._is_connection_alive(conn):
                    return conn
                # 如果连接已断开，关闭它并尝试获取下一个连接
                conn.close()
            # 如果连接池为空或所有连接都已断开，创建新连接
            return self._create_connection()
    
    def return_connection(self, conn):
        with self.lock:
            # 检测连接是否存活，只将存活的连接归还到连接池
            if self._is_connection_alive(conn) and len(self.connections) < self.max_connections:
                self.connections.append(conn)
            else:
                conn.close()

# 创建全局数据库连接池
db_pool = DatabasePool()

class DatabaseTool:
    """数据库操作工具类，提供简化的数据库操作方法"""
    
    @staticmethod
    def execute_query(sql, params=None):
        """
        执行查询SQL语句
        
        Args:
            sql: SQL查询语句
            params: SQL参数（可选）
            
        Returns:
            查询结果列表
        """
        conn = db_pool.get_connection()
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            result = cursor.fetchall()
            return result
        finally:
            db_pool.return_connection(conn)
    
    @staticmethod
    def execute_one(sql, params=None):
        """
        执行查询SQL语句，返回第一条结果
        
        Args:
            sql: SQL查询语句
            params: SQL参数（可选）
            
        Returns:
            查询结果的第一条记录，或None
        """
        conn = db_pool.get_connection()
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            result = cursor.fetchone()
            return result
        finally:
            db_pool.return_connection(conn)
    
    @staticmethod
    def execute_update(sql, params=None):
        """
        执行更新SQL语句（INSERT、UPDATE、DELETE等）
        
        Args:
            sql: SQL更新语句
            params: SQL参数（可选）
            
        Returns:
            受影响的行数
        """
        conn = db_pool.get_connection()
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            conn.commit()
            return cursor.rowcount
        finally:
            db_pool.return_connection(conn)
    
    @staticmethod
    def execute_many(sql, params_list):
        """
        批量执行SQL语句
        
        Args:
            sql: SQL语句
            params_list: 参数列表
            
        Returns:
            受影响的行数
        """
        conn = db_pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.executemany(sql, params_list)
            conn.commit()
            return cursor.rowcount
        finally:
            db_pool.return_connection(conn)
    
    @staticmethod
    def execute_script(sql_script):
        """
        执行SQL脚本
        
        Args:
            sql_script: SQL脚本内容
        """
        conn = db_pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.executescript(sql_script)
            conn.commit()
        finally:
            db_pool.return_connection(conn)

# 创建全局数据库工具实例
db_tool = DatabaseTool()