from pydantic import BaseModel, field_validator

# 輸出 Schema
class Feature(BaseModel):
    type: str = "Feature"
    properties: dict
    geometry: dict

class FeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[Feature]

# 輸入 Schema
class RegionQuery(BaseModel):
    type: str = "Feature"
    geometry: dict

    @field_validator('geometry')
    @classmethod
    def validate_epsg4326(cls, v):
        """強制檢查：確保傳入的座標系統符合 EPSG:4326 的經緯度合理範圍"""
        geom_type = v.get("type")
        if geom_type not in ["Polygon", "MultiPolygon"]:
            raise ValueError("幾何類型必須為 Polygon 或 MultiPolygon")
        
        try:
            if geom_type == "Polygon":
                first_coord = v["coordinates"][0][0]
            else:
                first_coord = v["coordinates"][0][0][0]
                
            lon, lat = first_coord[0], first_coord[1]
            if not (-180 <= lon <= 180) or not (-90 <= lat <= 90):
                raise ValueError(f"座標數值異常 (經度: {lon}, 緯度: {lat})，請確認是否為 EPSG:4326 投影")
        except (KeyError, IndexError, TypeError):
            raise ValueError("GeoJSON 座標結構解析失敗")
            
        return v