# Phase 0

## Ingesting data

- Download the dataset from 'data\source\data.txt'
- Create and EC2 instance > docker container > mcr.microsoft.com/mssql/server:2022-latest
- Spin up the Legacy MSSQL Server
```
docker run -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=FDE@2026" -p 1433:1433 --name legacy-mssql -d mcr.microsoft.com/mssql/server:2022-latest
```
- install the req > pip install -r requirements.txt

- python scripts\ingest_legacy_data.py
