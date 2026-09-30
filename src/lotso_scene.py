"""Lightweight animated Lotso scene using a sourced, unretouched full-body image."""
import math
import time
from pathlib import Path
from PIL import Image, ImageTk
import tkinter as tk


def rounded(canvas, x1, y1, x2, y2, radius=16, **options):
    return canvas.create_polygon(x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,
        x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,
        x1,y1+radius,x1,y1, smooth=True, splinesteps=24, **options)


class SoftButton(tk.Canvas):
    def __init__(self, master, **kw):
        self.text = kw.pop('text', '')
        self.command = kw.pop('command', lambda: None)
        self.fill = kw.pop('bg', '#276ABC')
        self.fg = kw.pop('fg', 'white')
        self.hover_fill = kw.pop('activebackground', self.fill)
        self.font = kw.pop('font', ('Microsoft YaHei UI', -15, 'bold'))
        self.disabled = False
        self.hover = False
        super().__init__(master, height=48, highlightthickness=0, bg=master.cget('bg'),
                         cursor='hand2', takefocus=True)
        self.bind('<Configure>', lambda e: self.draw())
        self.bind('<Enter>', lambda e: self.set_hover(True))
        self.bind('<Leave>', lambda e: self.set_hover(False))
        self.bind('<ButtonRelease-1>', lambda e: self.invoke())
        self.bind('<Return>', lambda e: self.invoke())
        self.bind('<space>', lambda e: self.invoke())
    def set_hover(self, value):
        self.hover = value
        self.draw()
    def invoke(self):
        if not self.disabled:
            self.command()
    def config(self, **kw):
        if 'text' in kw:
            self.text = kw.pop('text')
        if 'state' in kw:
            self.disabled = kw.pop('state') == 'disabled'
        if kw:
            super().config(**kw)
        self.draw()
    def draw(self):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        color = '#BBCDE0' if self.disabled else self.hover_fill if self.hover else self.fill
        rounded(self, 0, 0, w, h, 16, fill=color, outline='')
        self.create_text(w/2, h/2, text=self.text, fill=self.fg, font=self.font)


class LotsoScene:
    def __init__(self, canvas, enabled):
        self.canvas = canvas
        self.enabled = enabled
        self.frame = 0
        self.started = time.monotonic()
        self.hug_until = 0
        self.last_hug = False
        self.frames = []
        image = Image.open(Path(__file__).with_name('assets-v3') / 'lotso.png').convert('RGB')
        # Rendering transforms only: preserve the original image and full character.
        for index in range(32):
            phase = index * math.tau / 32
            side = round(250 + 3 * math.sin(phase))
            tile = Image.new('RGB', (264, 264), 'white')
            rendered = image.resize((side, side), Image.Resampling.LANCZOS)
            tile.paste(rendered, ((264-side)//2, (264-side)//2))
            tile = tile.rotate(1.2 * math.sin(phase), Image.Resampling.BICUBIC, fillcolor='white')
            self.frames.append(ImageTk.PhotoImage(tile))
        self.friends = {}
        for name, side in [('woody', 164), ('buzz', 164), ('alien', 86)]:
            friend = Image.open(Path(__file__).with_name('assets-v3') / (name + '.png')).convert('RGB')
            self.friends[name] = ImageTk.PhotoImage(friend.resize((side, side), Image.Resampling.LANCZOS))
        self.canvas.bind('<Button-1>', self.hug)
        self.canvas.after(90, self.tick)

    def hug(self, event):
        if 70 < event.y < 390:
            self.hug_until = time.monotonic() + 2.6
            self.draw()

    def draw(self):
        c=self.canvas
        c.delete('all')
        w,h=c.winfo_width(),c.winfo_height()
        t=time.monotonic()-self.started
        moving=self.enabled()
        greeting=time.monotonic()<self.hug_until
        bob=3*math.sin(t*1.8) if moving else 0
        if greeting and moving:
            bob-=9*abs(math.sin(t*5))
        c.create_image(w/2,h*.40+bob,image=self.frames[self.frame if moving else 0])
        # Full-body friends occupy the illustration column, outside all controls.
        for name,x,y,phase in [('woody',w*.26,h*.81,0),('buzz',w*.74,h*.81,2),('alien',w*.25,h*.10,4)]:
            offset = 2 * math.sin(t*1.8+phase) if moving else 0
            c.create_image(x,y+offset,image=self.friends[name])
        c.create_text(w*.76,h*.10,text='★',fill='#F5C747',font=('Segoe UI Symbol',-25))
        if greeting and moving:
            for i in range(4):
                a=t*2+i*math.tau/4
                c.create_text(w/2+123*math.cos(a),h*.40+118*math.sin(a),text='★',fill='#EDBC3F',font=('Segoe UI Symbol',-14))

    def tick(self):
        try:
            if self.canvas.winfo_toplevel().state() != 'iconic':
                hugging = time.monotonic() < self.hug_until
                if self.enabled():
                    self.frame = (self.frame + 1) % len(self.frames)
                if self.enabled() or self.last_hug != hugging:
                    self.draw()
                self.last_hug = hugging
            self.canvas.after(90, self.tick)
        except tk.TclError:
            pass
