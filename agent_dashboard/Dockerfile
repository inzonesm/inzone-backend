# FROM python:3.12-slim
FROM gcr.io/inzone-f93e4/agent-dashboard:latest

WORKDIR /app

COPY . .

# RUN pip install -r requirements.txt

EXPOSE 8080

CMD streamlit run login.py --server.port 8080 --server.address 0.0.0.0
