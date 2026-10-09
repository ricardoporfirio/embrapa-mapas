"""Composição A4 inspirada no modelo cartográfico QGIS da Embrapa."""
from functools import lru_cache
from pathlib import Path
import os
import json
import math
from pyproj import Geod
from matplotlib.ticker import MaxNLocator

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps
from matplotlib import font_manager
from src.utils.atomic import atomic_output, project_path
from src.utils.classification import format_number

WIDTH, HEIGHT = 2480, 3508
MAP_FRAME = (154, 532, 2326, 2384)
FOOTER_TOP = 2560
LEGEND_LEFT, LEGEND_RIGHT = 1558, 2326


@lru_cache(maxsize=128)
def load_font(size, font_file="Arial.ttf"):
    bold = "bold" in font_file.lower()
    custom = project_path(font_file)
    candidates = [custom,
        Path(os.getenv("WINDIR", "C:/Windows")) / "Fonts" / ("arialbd.ttf" if bold else "arial.ttf"),
        Path("/usr/share/fonts/truetype/liberation2") / ("LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/liberation") / ("LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf")]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    fallback = font_manager.findfont(font_manager.FontProperties(family=["Arial", "Liberation Sans", "DejaVu Sans"], weight="bold" if bold else "normal"))
    return ImageFont.truetype(fallback, size)


def fit_font(draw, text, size, max_width, *, bold=False):
    name = "Arial-Bold.ttf" if bold else "Arial.ttf"
    while size > 16:
        font = load_font(size, name)
        if draw.textlength(str(text), font=font) <= max_width:
            return font
        size -= 1
    return load_font(size, name)


def text_top(draw, xy, text, font, *, center=False):
    draw.text(xy, str(text), font=font, fill="black", anchor="mt" if center else "lt")


def draw_centered_text(draw, text, font, y, color="black"):
    draw.text((WIDTH // 2, y), str(text), font=font, fill=color, anchor="mt")


def header(draw, title, subtitle, margin_top=154):
    # Mesmas linhas de texto recebidas do modelo; apenas tipografia e posição.
    font = fit_font(draw, title, 96, WIDTH - 308)
    draw_centered_text(draw, title, font, margin_top)
    subtitle_font = fit_font(draw, subtitle, 68, WIDTH - 308)
    draw_centered_text(draw, subtitle, subtitle_font, 302)
    return MAP_FRAME[1]


def content_crop(image):
    """Remove somente margens brancas, preservando a proporção da cartografia."""
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, "white")
    background.alpha_composite(rgba)
    rgb = background.convert("RGB")
    difference = ImageChops.difference(rgb, Image.new("RGB", rgb.size, "white"))
    mask = difference.convert("L").point(lambda value: 255 if value > 8 else 0)
    bounds = mask.getbbox()
    return rgb.crop(bounds) if bounds else rgb


def insert_image(img, draw, image_path, y_start=None, scale=None, border=3, border_color="black"):
    left, top, right, bottom = MAP_FRAME
    view = None
    with Image.open(project_path(image_path)) as source:
        metadata = source.info.get("embrapa_cartography")
        if metadata:
            info = json.loads(metadata)
            if info.get("crs") != "EPSG:4674":
                raise ValueError("O enquadramento cartográfico deve usar SIRGAS 2000.")
            xmin, xmax, ymin, ymax = info["extent"]
            x0, y0, width, height = info["axes"]
            # Pillow usa origem no topo; Matplotlib usa origem na base.
            crop = (round(x0*source.width), round((1-y0-height)*source.height),
                    round((x0+width)*source.width), round((1-y0)*source.height))
            content = source.crop(crop).convert("RGB")
            fitted = ImageOps.contain(content, (right-left,bottom-top), Image.Resampling.LANCZOS)
            x = left + (right-left-fitted.width)//2
            y = top + (bottom-top-fitted.height)//2
            sx = fitted.width/(xmax-xmin)
            sy = fitted.height/(ymax-ymin)
            view = {"extent": (xmin-(x-left)/sx, xmax+(right-x-fitted.width)/sx,
                               ymin-(bottom-y-fitted.height)/sy, ymax+(y-top)/sy),
                    "frame": MAP_FRAME}
        else:
            # Compatibilidade com imagens antigas: não inventa escala ou coordenadas.
            content = content_crop(source)
            fitted = ImageOps.contain(content, (right-left-72,bottom-top-72), Image.Resampling.LANCZOS)
            x = left + (right-left-fitted.width)//2
            y = top + (bottom-top-fitted.height)//2
    img.paste(fitted, (x,y))
    draw.rounded_rectangle(MAP_FRAME, radius=2, outline=border_color, width=border)
    return view


def coordinate_label(value, axis):
    if abs(value) < 1e-8:
        return "0.00°"
    direction = ("E" if value > 0 else "W") if axis == "longitude" else ("N" if value > 0 else "S")
    return f"{abs(value):.2f}°{direction}"


def geographic_ticks(minimum, maximum):
    ticks = MaxNLocator(nbins=3, steps=[1,2,2.5,5,10]).tick_values(minimum,maximum)
    margin=(maximum-minimum)*0.06
    return [float(value) for value in ticks if minimum+margin < value < maximum-margin]


def rotated_text(canvas, center, text, font):
    bounds=font.getbbox(text)
    layer=Image.new("RGBA",(math.ceil(font.getlength(text))+4,bounds[3]-bounds[1]+4),(0,0,0,0))
    ImageDraw.Draw(layer).text((2,2),text,font=font,fill="black",anchor="lt")
    layer=layer.rotate(90,expand=True)
    canvas.paste(layer,(round(center[0]-layer.width/2),round(center[1]-layer.height/2)),layer)


def coordinate_frame(canvas, view):
    draw=ImageDraw.Draw(canvas)
    xmin,xmax,ymin,ymax=view["extent"]
    left,top,right,bottom=view["frame"]
    font=load_font(42)
    for lon in geographic_ticks(xmin,xmax):
        x=left+(lon-xmin)/(xmax-xmin)*(right-left)
        draw.line((x,top-20,x,top),fill="black",width=3)
        draw.line((x,bottom,x,bottom+20),fill="black",width=3)
        label=coordinate_label(lon,"longitude")
        text_top(draw,(x,top-68),label,font,center=True)
        text_top(draw,(x,bottom+34),label,font,center=True)
    for lat in geographic_ticks(ymin,ymax):
        y=bottom-(lat-ymin)/(ymax-ymin)*(bottom-top)
        draw.line((left-20,y,left,y),fill="black",width=3)
        draw.line((right,y,right+20,y),fill="black",width=3)
        label=coordinate_label(lat,"latitude")
        rotated_text(canvas,(left-52,y),label,font)
        rotated_text(canvas,(right+52,y),label,font)


def scale_geometry(view, max_width=500):
    """Comprimento geodésico entre as extremidades, na latitude onde a barra aparece."""
    xmin,xmax,ymin,ymax=view["extent"]
    left,top,right,bottom=view["frame"]
    px_per_degree=(right-left)/(xmax-xmin)
    y=bottom-66
    latitude=ymin+(bottom-y)/(bottom-top)*(ymax-ymin)
    end_x=right-180
    end_lon=xmin+(end_x-left)/px_per_degree
    geod=Geod(ellps="GRS80")
    span=max_width/px_per_degree
    maximum=abs(geod.inv(end_lon-span,latitude,end_lon,latitude)[2])/1000
    magnitude=10**math.floor(math.log10(maximum))
    distance=max(step*magnitude for step in (0.1,0.2,0.5,1,2,5,10) if step*magnitude <= maximum)
    low,high=0.0,span
    for _ in range(50):
        middle=(low+high)/2
        metres=abs(geod.inv(end_lon-middle,latitude,end_lon,latitude)[2])
        if metres < distance*1000:
            low=middle
        else:
            high=middle
    width=(low+high)/2*px_per_degree
    return {"x":end_x-width,"y":y,"width":width,"km":distance,"latitude":latitude}


def scale_bar(canvas, view):
    draw=ImageDraw.Draw(canvas)
    scale=scale_geometry(view)
    x,y,width=scale["x"],scale["y"],scale["width"]
    font=load_font(46)
    draw.rectangle((x-38,y-90,x+width+125,y+56),fill="white")
    draw.rectangle((x,y,x+width/2,y+24),fill="black",outline="black",width=3)
    draw.rectangle((x+width/2,y,x+width,y+24),fill="white",outline="black",width=3)
    for position,label in ((x,"0"),(x+width/2,format_number(scale["km"]/2)),
                           (x+width,format_number(scale["km"])+" km")):
        text_top(draw,(position,y-70),label,font,center=True)
    label=f"Escala em {coordinate_label(scale['latitude'],'latitude')}"
    text_top(draw,(x+width/2,y+34),label,load_font(24),center=True)


def paste_logo(canvas, path, bounds):
    with Image.open(project_path(path)) as source:
        logo = content_crop(source).convert("RGBA")
    left, top, right, bottom = bounds
    logo = ImageOps.contain(logo, (right-left,bottom-top), Image.Resampling.LANCZOS)
    canvas.paste(logo, (left+(right-left-logo.width)//2, top+(bottom-top-logo.height)//2), logo)


def left_side(base_img, draw):
    font = load_font(44)
    lines = ["Sistema de coordenadas geográficas", "(Lat/Long) Datum SIRGAS 2000",
             "Fonte: IBGE", "Elaboração: Embrapa Gado de Leite"]
    for index,line in enumerate(lines):
        text_top(draw, (154,FOOTER_TOP+index*53), line, font)
    # Caixas independentes evitam que as dimensões originais alterem os alinhamentos.
    paste_logo(base_img, "static/images/embrapa.jpg", (204,3070,610,3222))
    paste_logo(base_img, "static/images/cileite.jpg", (842,2950,1320,3252))


def legend_labels(bins):
    labels=[]
    previous=None
    for limit in bins:
        if limit == float("inf"):
            labels.append("Todos os valores" if previous is None else f"Acima de {format_number(previous)}")
        elif previous is None:
            labels.append(f"Até {format_number(limit)}")
        else:
            labels.append(f"{format_number(previous)} - {format_number(limit)}")
        previous=limit
    return labels


def right_side(draw, title, measure_unit, bins, colors, year=None):
    if len(colors) != len(bins):
        raise ValueError("Cada classe da legenda deve ter exatamente uma cor.")
    center=(LEGEND_LEFT+LEGEND_RIGHT)//2
    width=LEGEND_RIGHT-LEGEND_LEFT
    text_top(draw, (center,2578), title, fit_font(draw,title,64,width,bold=True), center=True)
    unit=f"( {measure_unit} )"
    text_top(draw, (center,2660), unit, fit_font(draw,unit,48,width), center=True)
    if year is not None:
        text_top(draw,(LEGEND_LEFT,2772),f"Ano: {year}",load_font(60,"Arial-Bold.ttf"))
    labels=legend_labels(bins)+["Sem informação"]
    palette=list(colors)+["#cccccc"]
    start=2860
    row=min(94,(HEIGHT-190-start)//len(labels))
    swatch_width=118
    swatch_height=min(60,row-12)
    text_width=width-swatch_width-24
    font_size=min(48,max(22,row-12))
    for index,(label,color) in enumerate(zip(labels,palette)):
        y=start+index*row
        draw.rectangle((LEGEND_LEFT,y,LEGEND_LEFT+swatch_width,y+swatch_height),fill=color)
        font=fit_font(draw,label,font_size,text_width)
        # Alinhamento vertical pelo topo real dos glifos, sem deslocamento da fonte.
        bounds=draw.textbbox((0,0),label,font=font,anchor="lt")
        text_top(draw,(LEGEND_LEFT+swatch_width+24,y+(swatch_height-(bounds[3]-bounds[1]))//2),label,font)


def rose_compass(base_img):
    draw=ImageDraw.Draw(base_img)
    center=2218
    text_top(draw,(center,570),"N",load_font(40),center=True)
    draw.polygon([(center,615),(center-46,720),(center,680),(center+46,720)],fill="black")


def render_poster(title, subtitle, image_path, legend_title, measure_unit, bins, colors, year, output):
    img=Image.new("RGB",(WIDTH,HEIGHT),"white")
    draw=ImageDraw.Draw(img)
    header(draw,title,subtitle)
    view=insert_image(img,draw,image_path)
    if view is not None:
        coordinate_frame(img,view)
        scale_bar(img,view)
    rose_compass(img)
    left_side(img,draw)
    right_side(draw,legend_title,measure_unit,bins,colors,year)
    with atomic_output(output) as temporary:
        img.save(temporary,dpi=(300,300))
