from flask import Flask, request, jsonify, redirect
import redis
import mysql.connector
import string
import random
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

app = Flask(__name__)

# 配置Redis连接
redis_client = redis.Redis(
    host='192.168.10.5',
    port=6379,
    decode_responses=True
)

# 配置MySQL连接
# 先连接到MySQL服务器（不指定数据库）
temp_connection = mysql.connector.connect(
    host='192.168.10.5',
    port=3306,
    user='root',
    password='123456'
)
temp_cursor = temp_connection.cursor()

# 创建数据库（如果不存在）
temp_cursor.execute("CREATE DATABASE IF NOT EXISTS shortener")
temp_connection.close()

# 连接到shortener数据库
mysql_connection = mysql.connector.connect(
    host='192.168.10.5',
    port=3306,
    user='root',
    password='123456',
    database='shortener'
)
mysql_cursor = mysql_connection.cursor()

# 生成唯一的短链接ID
def generate_short_id(length=6):
    characters = string.ascii_letters + string.digits
    while True:
        short_id = ''.join(random.choice(characters) for _ in range(length))
        if not redis_client.exists(short_id):
            return short_id

# 创建数据表
def create_tables():
    create_table_query = """
    CREATE TABLE IF NOT EXISTS urls (
        id INT AUTO_INCREMENT PRIMARY KEY,
        short_id VARCHAR(20) UNIQUE NOT NULL,
        long_url TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    mysql_cursor.execute(create_table_query)
    mysql_connection.commit()

# 初始化数据表
create_tables()

# 健康检查接口
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'})

# 生成短链接接口
@app.route('/shorten', methods=['POST'])
def shorten_url():
    data = request.get_json()
    if not data or 'long_url' not in data:
        return jsonify({'error': 'Missing long_url parameter'}), 400
    
    long_url = data['long_url']
    
    # 检查Redis中是否已存在该长链接
    existing_short_id = redis_client.get(f'long_to_short:{long_url}')
    if existing_short_id:
        short_url = f"http://localhost:5000/{existing_short_id}"
        return jsonify({'short_url': short_url})
    
    # 生成新的短链接ID
    short_id = generate_short_id()
    
    # 存储到Redis
    redis_client.set(short_id, long_url)
    redis_client.set(f'long_to_short:{long_url}', short_id)
    redis_client.expire(short_id, 86400)  # 24小时过期
    redis_client.expire(f'long_to_short:{long_url}', 86400)  # 24小时过期
    
    # 存储到MySQL
    insert_query = "INSERT INTO urls (short_id, long_url) VALUES (%s, %s)"
    mysql_cursor.execute(insert_query, (short_id, long_url))
    mysql_connection.commit()
    
    # 构建短链接URL
    short_url = f"http://localhost:5000/{short_id}"
    
    return jsonify({'short_url': short_url})

# 短链接重定向接口
@app.route('/<short_id>', methods=['GET'])
def redirect_url(short_id):
    # 从Redis中获取长链接
    long_url = redis_client.get(short_id)
    
    # 如果Redis中不存在，从MySQL中查询
    if not long_url:
        select_query = "SELECT long_url FROM urls WHERE short_id = %s"
        mysql_cursor.execute(select_query, (short_id,))
        result = mysql_cursor.fetchone()
        if not result:
            return jsonify({'error': 'Short URL not found'}), 404
        long_url = result[0]
        # 将结果缓存到Redis
        redis_client.set(short_id, long_url)
        redis_client.expire(short_id, 86400)  # 24小时过期
    
    # 重定向到长链接
    return redirect(long_url, code=302)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)