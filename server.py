import os
import requests
import uvicorn
from datetime import datetime
from mcp.server.fastmcp import FastMCP

# 1. MCP 서버 초기화
mcp = FastMCP("Verkada_Camera_Alerts")

# 2. 환경변수에서 Verkada API 키 가져오기
VERKADA_API_KEY = os.environ.get("VERKADA_API_KEY")
BASE_URL = "https://api.verkada.com/cameras/v1/alerts" 
HEADERS = {
    "accept": "application/json",
    "x-api-key": VERKADA_API_KEY
}

# 3. AI가 사용할 도구(Tool) 정의
@mcp.tool()
def get_camera_alerts(start_time_iso: str, end_time_iso: str, notification_type: str = "") -> str:
    """
    특정 시간 범위 내의 Verkada 카메라 알림(Alerts) 이벤트를 조회합니다.
    """
    if not VERKADA_API_KEY:
        return "오류: 서버에 VERKADA_API_KEY 환경변수가 설정되지 않았습니다."

    try:
        # ISO 8601 문자열 -> Unix Timestamp 변환
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
        
        # 페이징(Pagination) 처리
        while True:
            response = requests.get(BASE_URL, headers=HEADERS, params=params)
            response.raise_for_status()
            data = response.json()
            
            alerts = data.get("alerts", [])
            all_alerts.extend(alerts)
            
            next_page_token = data.get("next_page_token")
            if not next_page_token:
                break
            params["page_token"] = next_page_token

        if not all_alerts:
            return f"해당 기간({start_time_iso} ~ {end_time_iso})에 발생한 알림이 없습니다."

        # 결과 요약
        summary = {
            "total_count": len(all_alerts),
            "alert_types_count": {},
            "sample_details": [] 
        }
        
        for idx, a in enumerate(all_alerts):
            a_type = a.get("notification_type", "unknown")
            summary["alert_types_count"][a_type] = summary["alert_types_count"].get(a_type, 0) + 1
            
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

# 4. 서버 실행 (Render 환경 호환)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Starting MCP Server on 0.0.0.0:{port} using Uvicorn...")
    
    app = getattr(mcp, "sse_app", None)
    if callable(app):
        app = app()
    elif app_attr := getattr(mcp, "_app", None):
        app = app_attr

    uvicorn.run(app, host="0.0.0.0", port=port)
