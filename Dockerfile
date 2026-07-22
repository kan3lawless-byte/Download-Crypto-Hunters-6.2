FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8501
ENV WEBHOOK_PORT=8000
EXPOSE 8501 8000
CMD ["python", "launcher.py"]
