FROM python:3-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py .

RUN useradd -m flask
USER flask

EXPOSE 5000

CMD ["flask", "run", "--host=0.0.0.0"]