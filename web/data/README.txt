把 Natural Earth 的「陆地轮廓」GeoJSON 放在这个目录，文件名必须是 world.geo.json，刷新页面即生效。

只用陆地，不用国界
------------------
需要的是 ne_110m_land.geojson —— 只有陆地块，没有任何国界线。
下载页：https://www.naturalearthdata.com/downloads/110m-physical-vectors/
在页面里选 "Land"，下载 GeoJSON 版本，改名 world.geo.json 放进本目录。

约 200 KB。想更清晰可换 50m 版本（约 4 MB），代价是首屏解析略慢。

不要用 admin_0_countries —— 那个含国界，会画出各国边界。

格式要求
--------
FeatureCollection 或单个 Feature，geometry 为 Polygon / MultiPolygon，
坐标为 WGS84 经纬度 [lon, lat]，不需要任何属性字段。

没有这个文件时
--------------
地图自动退化为经纬网格 + 机场点，玩法完全不受影响，只是没有陆地轮廓。

合规提示
--------
ne_110m_land 只包含陆地，不涉及国界画法，可自由使用与分发。
