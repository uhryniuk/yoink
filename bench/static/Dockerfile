FROM python:3.11-slim AS generator
WORKDIR /gen
COPY generate.py .
RUN python generate.py

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=generator /gen/html /usr/share/nginx/html
EXPOSE 80
