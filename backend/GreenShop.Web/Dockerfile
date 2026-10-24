FROM mcr.microsoft.com/dotnet/sdk:8.0@sha256:f7e28a0a3f6f9235929ec19274fd0ddf8534e9159f99fac602ac73304f1ce99f AS build
WORKDIR /src

COPY ["GreenShop.Web/GreenShop.Web.csproj", "GreenShop.Web/"]
RUN dotnet restore "GreenShop.Web/GreenShop.Web.csproj"

COPY . .
WORKDIR "/src/GreenShop.Web"
RUN dotnet build "GreenShop.Web.csproj" -c Release -o /app/build

FROM build AS publish
RUN dotnet publish "GreenShop.Web.csproj" -c Release -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:8.0@sha256:1601380775673021a23ea5985669f1daf03719faaa684f839da1752fb48cfc7f AS final
WORKDIR /app
COPY --from=publish /app/publish .

RUN mkdir -p /app/keys /app/wwwroot/uploads/products && chown app:app /app/keys /app/wwwroot/uploads/products
USER app

# Mở cổng web bên trong container
EXPOSE 8080
ENV ASPNETCORE_URLS=http://+:8080

ENTRYPOINT ["dotnet", "GreenShop.Web.dll"]
