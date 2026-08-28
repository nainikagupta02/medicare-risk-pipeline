FROM python:3.11-slim

# xgboost and lightgbm both link against libgomp for openmp-based
# multithreading -- python:slim doesn't ship it by default
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8888

# token disabled for local convenience -- do not expose this container to an
# untrusted network without adding auth back
CMD ["jupyter", "notebook", "--ip=0.0.0.0", "--port=8888", "--no-browser", \
     "--allow-root", "--NotebookApp.token="]
