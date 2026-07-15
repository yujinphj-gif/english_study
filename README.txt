===== 영단어 공부방 설치 및 실행 방법 =====

[1] 패키지 설치]
  pip install -r requirements.txt

[2] MSSQL 설정]
  config.py 파일을 열어 아래 항목을 본인 환경에 맞게 수정하세요:
    - server   : MSSQL 서버 주소 (예: localhost, 192.168.1.10\SQLEXPRESS)
    - database : 데이터베이스 이름 (EnglishStudy 권장)
    - username : DB 사용자 이름
    - password : DB 비밀번호
    - driver   : 설치된 ODBC 드라이버 이름
    - trusted_connection : Windows 인증을 사용할 경우 True로 변경

  드라이버 목록 확인 (PowerShell):
    python -c "import pyodbc; print(pyodbc.drivers())"

  만약 SQL Server 인증을 사용할 경우, config.py의 username/password를 정확히 입력하세요.
  Windows 인증(Integrated Security)을 사용할 경우 username/password를 빈 문자열로 두고
  trusted_connection을 True로 설정하거나 환경 변수 DB_TRUSTED_CONNECTION=1을 사용하세요.

[3] 데이터베이스 생성 (SSMS 또는 쿼리)]
  CREATE DATABASE EnglishStudy;

[4] 앱 실행]
  python app.py

  브라우저에서 http://localhost:5000 접속

[주요 기능]
  - 단어 추가 / 수정 / 삭제
  - 카테고리별 분류
  - 난이도 설정 (별 1~5개)
  - 4지선다 퀴즈 (정답률, 연속 정답 추적)
  - 단어 검색 및 필터
