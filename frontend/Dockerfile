# 基础镜像按 digest 固定（原 tag：node:22.23.3-alpine3.24，取值日期 2026-11-11）：
# 浮动标签会在上游重发时悄悄换掉 Node 版本与 Alpine 基线，tag 也会被重指到别的镜像；
# digest 内容不可变，构建产物才可复现、能排查。
# 升级请手动改这一行：docker buildx imagetools inspect node:22.23.3-alpine3.24 取新 digest。
FROM node@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# 版本号由 make build 经 docker-compose 的 web.build.args 注入（仓库根的 Makefile 能读到 .git，
# 构建上下文里没有）。直接 docker compose build 时为空串，由 vite.config.js 用时间戳兜底。
ARG APP_VERSION=""
# 显式在命令里引用 $APP_VERSION：让 ARG 值进入本层缓存键，改了 sha 就一定重建。
# dist/version.txt 由 vite 插件写出，与注入 bundle 的是同一个值；
# test -s 保证插件一旦失效构建就失败，而不是部署一个永远探测不到版本的产物。
RUN APP_VERSION="$APP_VERSION" npm run build && test -s dist/version.txt

# 同上：nginx 也按 digest 固定（原 tag：nginx:1.27.5-alpine3.21，取值日期 2026-11-11）。
FROM nginx@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10
# 中国上海时区：nginx 访问/错误日志的时间戳按本地时间走。基础镜像自带 tzdata
# （/usr/share/zoneinfo），所以只设环境变量 + 指向时区文件。
ENV TZ=Asia/Shanghai
RUN cp /usr/share/zoneinfo/$TZ /etc/localtime
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 443
