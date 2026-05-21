FROM nginx:alpine

# Copiar el dashboard
COPY index.html /usr/share/nginx/html/index.html

# Configuración mínima de nginx para SPA
RUN echo 'server { \
    listen $PORT; \
    root /usr/share/nginx/html; \
    location / { try_files $uri $uri/ /index.html; } \
    location /health { return 200 "ok"; } \
}' > /etc/nginx/templates/default.conf.template

EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
