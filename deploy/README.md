# Cloud deployment

The production layout keeps the graph UI at `/` and exposes Tutor at `/tutor/`.
Neo4j, the graph API, and Tutor remain bound to loopback; only Nginx listens on
public HTTP/HTTPS ports.

Install the service and Nginx templates after replacing the application checkout:

```bash
sudo install -m 0644 deploy/knowledge-graph-api.service /etc/systemd/system/
sudo install -m 0644 deploy/adaptive-tutor.service /etc/systemd/system/
sudo install -m 0644 deploy/nginx-knowledge-graph.conf \
  /etc/nginx/sites-available/knowledge-graph
sudo ln -sfn /etc/nginx/sites-available/knowledge-graph \
  /etc/nginx/sites-enabled/knowledge-graph
sudo systemctl daemon-reload
sudo nginx -t
sudo systemctl enable --now knowledge-graph-api adaptive-tutor nginx
```

Server-only configuration must set at least `NEO4J_PASSWORD`,
`DEEPSEEK_API_KEY`, `GRAPH_BASE_URL=http://127.0.0.1:8000/api/v1`, and the
public `GRAPH_FRONTEND_URL`. Never commit `.env` files or database dumps.
