"""Small canvas toys decorating the blue title band."""
import math


def draw_toys(c, width):
    def star(x, y, r, fill, points=5):
        coords = []
        for i in range(points * 2):
            a = -math.pi / 2 + i * math.pi / points
            radius = r if i % 2 == 0 else r * .45
            coords.extend((x + math.cos(a) * radius, y + math.sin(a) * radius))
        c.create_polygon(*coords, fill=fill, outline='', tags='decoration')

    def oval(*coords, **kw):
        c.create_oval(*coords, outline='', tags='decoration', **kw)

    def poly(*coords, **kw):
        c.create_polygon(*coords, outline='', tags='decoration', **kw)

    span = max(540, width - 410)
    # A sheriff badge, a little green alien, the yellow toy ball, and a rocket.
    x, y = 325, 53
    star(x, y, 30, '#F9CF4D', 6)
    oval(x-13,y-13,x+13,y+13,fill='#E7AC34')
    star(x,y,10,'#FFF0A4')

    x = 325 + span * .28
    poly(x-25,52,x-44,37,x-24,39,fill='#B9DD58')
    poly(x+25,52,x+44,37,x+24,39,fill='#B9DD58')
    oval(x-21,54,x+21,86,fill='#305CA5')
    poly(x-22,62,x+22,62,x+20,70,x-20,70,fill='#9D79C2')
    oval(x-10,78,x-1,89,fill='#A9CF46')
    oval(x+1,78,x+10,89,fill='#A9CF46')
    c.create_line(x,33,x,22,fill='#B9DD58',width=3,tags='decoration')
    oval(x-4,17,x+4,25,fill='#D1E97C')
    oval(x-29,31,x+29,62,fill='#B9DD58')
    for dx in (-16,0,16):
        oval(x+dx-7,37,x+dx+7,50,fill='#FFFFFF')
        oval(x+dx-2,40,x+dx+3,46,fill='#233F58')
    c.create_arc(x-9,46,x+9,56,start=190,extent=160,style='arc',outline='#527344',width=2,tags='decoration')

    x, y = 325 + span * .57, 54
    oval(x-29,y-29,x+29,y+29,fill='#FFDC55')
    c.create_arc(x-27,y-28,x+28,y+28,start=55,extent=230,style='arc',outline='#346EB9',width=10,tags='decoration')
    star(x+5,y,17,'#D94E42')

    x, y = 325 + span * .85, 52
    poly(x-8,y+24,x,y+47,x+8,y+24,fill='#FFD14E')
    poly(x-5,y+24,x,y+38,x+5,y+24,fill='#EF8050')
    poly(x-12,y+6,x-27,y+28,x-10,y+24,fill='#D7554B')
    poly(x+12,y+6,x+27,y+28,x+10,y+24,fill='#D7554B')
    oval(x-14,y-24,x+14,y+30,fill='#EDF6F9')
    poly(x-12,y-13,x,y-36,x+12,y-13,fill='#D7554B')
    oval(x-9,y-9,x+9,y+9,fill='#7EC5DF')
    oval(x-5,y-6,x+2,y+1,fill='#DDF4FA')
    for x,y,r in [(385,27,5),(420,81,4),(width-106,25,5),(width-292,91,4)]:
        star(x,y,r,'#FFECA0')
