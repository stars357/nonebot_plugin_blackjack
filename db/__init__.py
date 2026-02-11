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
    
    def get_connection(self):
        with self.lock:
            if self.connections:
                return self.connections.pop()
            else:
                return self._create_connection()
    
    def return_connection(self, conn):
        with self.lock:
            if len(self.connections) < self.max_connections:
                self.connections.append(conn)
            else:
                conn.close()

# 创建全局数据库连接池
db_pool = DatabasePool()