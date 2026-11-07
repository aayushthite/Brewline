FROM python:3.12-slim
WORKDIR /app
COPY loadgen.py .
RUN useradd --create-home appuser
USER appuser
CMD ["python", "-u", "loadgen.py"]
