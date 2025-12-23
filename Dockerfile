FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

#This automatically runs the given script when it is uncommented 
CMD ["python", "src/demo.py"]
#CMD ["python", "src/sleep_data_export.py"]
