FROM python:3.12-slim
RUN useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=user . .
RUN chown -R user /app
USER user
RUN python tools/build_demo.py
ENV PUBLIC_DEMO=1 CONTROL_ROOM_HOST=0.0.0.0 CONTROL_ROOM_PORT=7860
EXPOSE 7860
CMD ["python", "-m", "app.server"]
