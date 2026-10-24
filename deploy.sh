docker stop server_management_django || true
docker rm server_management_django || true

# Stop and remove old container name if it exists (to free up port 8056)
docker stop devops_tracker_django || true
docker rm devops_tracker_django || true

# Assuming you run this from the project root (where the Dockerfile is)
docker build -t server_management_django .

# If you want to expose it on port 8055 of the host server, use -p 8055:8000
docker run -d --name server_management_django -p 8056:8056 --network pgnet -v /etc/localtime:/etc/localtime:ro server_management_django