import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

# MSSQL 연결 설정 - .env 파일 또는 환경변수로 재정의하세요
DB_CONFIG = {
    "server": "localhost",       # MSSQL 서버 주소
    "database": "EnglishStudy",  # 데이터베이스 이름
    "username": "sa",            # SQL Server 사용자 이름 (SQL 인증)
    "password": "your_password", # SQL Server 비밀번호 (SQL 인증)
    "driver": "ODBC Driver 17 for SQL Server",  # 설치된 드라이버 이름
    "trusted_connection": True,   # Windows 인증을 사용할 경우 True로 변경
}

SECRET_KEY = os.getenv("SECRET_KEY", "english_study_secret_key_change_me")


def get_connection():
    driver = os.getenv("DB_DRIVER", DB_CONFIG["driver"])
    server = os.getenv("DB_SERVER", DB_CONFIG["server"])
    database = os.getenv("DB_DATABASE", DB_CONFIG["database"])
    username = os.getenv("DB_USERNAME", DB_CONFIG["username"])
    password = os.getenv("DB_PASSWORD", DB_CONFIG["password"])
    trusted_env = os.getenv("DB_TRUSTED_CONNECTION")
    if trusted_env is not None:
        trusted_connection = trusted_env.lower() in ("1", "true", "yes", "y")
    else:
        trusted_connection = DB_CONFIG["trusted_connection"]

    conn_parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={server}",
        f"DATABASE={database}",
        "TrustServerCertificate=yes",
    ]

    if trusted_connection:
        conn_parts.append("Trusted_Connection=yes")
    else:
        conn_parts.append(f"UID={username}")
        conn_parts.append(f"PWD={password}")

    conn_str = ";".join(conn_parts)
    return pyodbc.connect(conn_str)


def init_db():
    """테이블 초기화 - 최초 실행 시 한 번만"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Lessons' AND xtype='U')
        CREATE TABLE Lessons (
            id INT IDENTITY(1,1) PRIMARY KEY,
            name NVARCHAR(100) NOT NULL UNIQUE,
            created_at DATETIME DEFAULT GETDATE()
        )
    """)

    cursor.execute("""
        IF NOT EXISTS (
            SELECT * FROM sys.columns
            WHERE object_id = OBJECT_ID('Lessons') AND name = 'sort_order'
        )
        ALTER TABLE Lessons ADD sort_order INT NULL
    """)
    cursor.execute("UPDATE Lessons SET sort_order = id WHERE sort_order IS NULL")

    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Words' AND xtype='U')
        CREATE TABLE Words (
            id INT IDENTITY(1,1) PRIMARY KEY,
            word NVARCHAR(200) NOT NULL,
            meaning NVARCHAR(500) NOT NULL,
            example_sentence NVARCHAR(1000),
            lesson_id INT FOREIGN KEY REFERENCES Lessons(id),
            created_at DATETIME DEFAULT GETDATE()
        )
    """)

    cursor.execute("""
        IF NOT EXISTS (
            SELECT * FROM sys.columns
            WHERE object_id = OBJECT_ID('Words') AND name = 'lesson_id'
        )
        ALTER TABLE Words ADD lesson_id INT NULL FOREIGN KEY REFERENCES Lessons(id)
    """)

    # 카테고리 FK 제약 제거 후 category_id 컬럼 삭제
    cursor.execute("""
        IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Words') AND name = 'category_id')
        BEGIN
            DECLARE @fk_name NVARCHAR(200)
            SELECT @fk_name = fk.name
            FROM sys.foreign_keys fk
            WHERE fk.parent_object_id = OBJECT_ID('Words')
              AND EXISTS (
                  SELECT 1 FROM sys.foreign_key_columns fkc
                  JOIN sys.columns c ON c.object_id = fkc.parent_object_id AND c.column_id = fkc.parent_column_id
                  WHERE fkc.constraint_object_id = fk.object_id AND c.name = 'category_id'
              )
            IF @fk_name IS NOT NULL
                EXEC('ALTER TABLE Words DROP CONSTRAINT ' + @fk_name)
            ALTER TABLE Words DROP COLUMN category_id
        END
    """)

    # 난이도 CHECK/DEFAULT 제약 제거 후 difficulty 컬럼 삭제
    cursor.execute("""
        IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Words') AND name = 'difficulty')
        BEGIN
            DECLARE @col_id INT = (
                SELECT column_id FROM sys.columns
                WHERE object_id = OBJECT_ID('Words') AND name = 'difficulty'
            )
            DECLARE @ck_name NVARCHAR(200)
            SELECT @ck_name = cc.name
            FROM sys.check_constraints cc
            WHERE cc.parent_object_id = OBJECT_ID('Words') AND cc.parent_column_id = @col_id
            IF @ck_name IS NOT NULL
                EXEC('ALTER TABLE Words DROP CONSTRAINT ' + @ck_name)

            DECLARE @df_name NVARCHAR(200)
            SELECT @df_name = dc.name
            FROM sys.default_constraints dc
            WHERE dc.parent_object_id = OBJECT_ID('Words') AND dc.parent_column_id = @col_id
            IF @df_name IS NOT NULL
                EXEC('ALTER TABLE Words DROP CONSTRAINT ' + @df_name)

            ALTER TABLE Words DROP COLUMN difficulty
        END
    """)

    cursor.execute("""
        IF EXISTS (SELECT * FROM sysobjects WHERE name='Categories' AND xtype='U')
            DROP TABLE Categories
    """)

    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='StudyHistory' AND xtype='U')
        CREATE TABLE StudyHistory (
            id INT IDENTITY(1,1) PRIMARY KEY,
            word_id INT FOREIGN KEY REFERENCES Words(id),
            is_correct BIT NOT NULL,
            studied_at DATETIME DEFAULT GETDATE()
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()
