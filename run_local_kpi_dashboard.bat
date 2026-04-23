@echo off
cd /d %~dp0
python -m pip install -r requirements_kpi_dashboard_v2.txt
streamlit run app_kpi_history.py --server.port 8501 --server.address 0.0.0.0
pause
