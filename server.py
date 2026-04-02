import os
import requests
import uvicorn
from datetime import datetime
from mcp.server.fastmcp import FastMCP

# 1. MCP 서버 초기화
mcp = FastMCP("Verkada_Camera_Alerts")

# 2. 환경변수에서 Verkada API 키 가져오기 (Render의 Environment Variables에 설정된 값)
VERKADA_API_KEY = os.environ.get("VERKADA_API_KEY")
BASE_URL = "https://api.verkada.com/cameras/v1/alerts" 
HEADERS = {
    "accept": "application/json",
    "x-api-key": VERKADA_API_KEY
}

# 3. AI가 사용할 도구(Tool) 정의
@mcp.tool()
def get_camera_alerts(start_time_iso: str, end_time_iso: str, notification_type: str = None) -> str:
    """
    특정 시간 범위 내의 Verkada 카메라 알림(Alerts) 이벤트를 조회합니다.
    
    :param start_time_iso: 시작 시간 (ISO 8601 형식, 예: "2026-04-01T00:00:00")
    :param end_time_iso: 종료 시간 (ISO 8601 형식, 예: "2026-04-01T23:59:59")
    :param notification_type: (선택) 쉼표로 구분된 알림 유형 
           지원 값: person_of_interest, license_plate_of_interest, tamper, crowd, 
                   motion, camera_offline, camera_online, line_crossing, loitering
    """
    if not VERKADA_API_KEY:
        return "오류: 서버에 VERKADA_API_KEY 환경변수가 설정되지 않았습니다. Render 설정에서 추가해주세요."

    try:
        # ISO 8601 문자열 -> Unix Timestamp(초 단위 정수)로 변환
        start_time_iso = start_time_iso.replace("Z", "+00:00")
        end_time_iso = end_time_iso.replace("Z", "+00:00")
        start_ts = int(datetime.fromisoformat(start_time_iso).timestamp())
        end_ts = int(datetime.fromisoformat(end_time_iso).timestamp())

        # API 파라미터 설정
        params = {
            "start_time": start_ts,
            "end_time": end_ts,
            "page_size": 200,
            "include_image_url": "false"
        }
        if notification_type:
            params["notification_type"] = notification_type.replace(" ", "")

        all_alerts = []
        
        # 데이터 조회 및 페이징(Pagination) 처리
        while True:
            response = requests.get(BASE_URL, headers=HEADERS, params=params)
            response.raise_for_status()
            data = response.json()
            
            alerts = data.get("alerts", [])
            all_alerts.extend(alerts)
            
            # 다음 페이지가 있는지 확인
            next_page_token = data.get("next_page_token")
            if not next_page_token:
                break
            params["page_token"] = next_page_token

        # 결과가 없을 때의 처리
        if not all_alerts:
            return f"해당 기간({start_time_iso} ~ {end_time_iso})에 발생한 알림이 없습니다."

        # LLM이 요약하기 쉽도록 결과 데이터 구조화
        summary = {
            "total_count": len(all_alerts),
            "alert_types_count": {},
            "sample_details": [] 
        }
        
        for idx, a in enumerate(all_alerts):
            a_type = a.get("notification_type", "unknown")
            summary["alert_types_count"][a_type] = summary["alert_types_count"].get(a_type, 0) + 1
            
            # 상세 내역은 컨텍스트 한도를 위해 최대 10개까지만 추가
            if idx < 10:
                occurred_at_ts = a.get("created_at") or a.get("timestamp")
                time_str = datetime.fromtimestamp(occurred_at_ts).strftime('%Y-%m-%d %H:%M:%S') if occurred_at_ts else "시간 불명"
                camera = a.get("camera_id", "알 수 없는 카메라")
                summary["sample_details"].append(f"[{time_str}] 카메라: {camera}, 유형: {a_type}")

        if len(all_alerts) > 10:
             summary["sample_details"].append(f"...외 {len(all_alerts) - 10}건 생략됨")

        return f"데이터 조회 성공. 요약 결과: {summary}"

    except Exception as e:
        return f"Verkada API 호출 중 오류가 발생했습니다: {str(e)}"

# 4. 서버 실행 (Render 배포 환경 호환 - Uvicorn 강제 설정 패치)
if __name__ == "__main__":
    # Render에서 할당한 포트 번호 가져오기 (기본값 8000)
    port = int(os.environ.get("PORT", "8000"))
    
    # FastMCP 내부에 숨겨진 uvicorn.run 함수를 가로채서 Render 환경에 맞게 강제 수정 (Monkey Patch)
    original_uvicorn_run = uvicorn.run
    
    def patched_run(*args, **kwargs):
        kwargs['host'] = '0.0.0.0'  # 외부에서 접속할 수 있도록 허용
        kwargs['port'] = port       # Render가 요구하는 포트 번호 주입
        original_uvicorn_run(*args, **kwargs)
        
    uvicorn.run = patched_run
    
    print(f"Starting MCP Server on 0.0.0.0:{port} using SSE...")
    
    # SSE 방식으로 실행
    mcp.run(transport='sse')
