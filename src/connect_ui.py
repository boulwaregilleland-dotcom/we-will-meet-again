"""Native, dependency-free interface for ECJTU Campus Connect."""
import json
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from lotso_scene import LotsoScene, SoftButton

BG = '#FFFFFF'
INK = '#183E6C'
MUTED = '#718299'
TEAL = '#276ABC'
LINE = '#D9E2EC'
FONT = 'Microsoft YaHei UI'


class ConnectUI:
    def __init__(self, app, preview=False):
        self.app = app
        self.preview = preview
        self.saved = {}
        self.events = queue.Queue()
        self.busy = False
        self.root = tk.Tk()
        self.root.title('我们将会再见')
        self.root.geometry('1040x660')
        self.root.minsize(1000, 660)
        self.root.configure(bg=BG)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.update_idletasks()
        x = max(0, (self.root.winfo_screenwidth() - 1040) // 2)
        y = max(0, (self.root.winfo_screenheight() - 710) // 2)
        self.root.geometry(f'+{x}+{y}')
        try:
            from pathlib import Path
            self.root.iconbitmap(str(Path(__file__).with_name('connect.ico')))
        except tk.TclError:
            pass
        if not preview and app.CONFIG.exists():
            try:
                self.saved = json.loads(app.protect(app.CONFIG.read_bytes(), decrypt=True))
            except Exception:
                pass
        self.service = tk.StringVar(value=self.saved.get('service', 'telecom'))
        if self.service.get() not in app.SERVICES:
            self.service.set('telecom')
        self.autostart = tk.BooleanVar(value=self.saved.get('autostart', True))
        self.reconnect = tk.BooleanVar(value=self.saved.get('reconnect', True))
        self.reveal = tk.BooleanVar(value=False)
        self.animation = tk.BooleanVar(value=self.saved.get('animation', True))
        self.transport = tk.StringVar(value=self.saved.get('transport', 'wired'))
        if self.transport.get() not in ('wired', 'wireless'):
            self.transport.set('wired')
        self.profiles = app.saved_profiles(self.saved)
        self.drafts = {}
        self.current_profile = None
        self.widgets = {}
        self.cards = {}
        self._layout()
        self.select_service(self.service.get())
        self.root.after(300, self.poll)

    def label(self, parent, text, size=14, color=INK, bold=False, **kw):
        return tk.Label(parent, text=text, font=(FONT, -size, 'bold' if bold else 'normal'),
                        fg=color, bg=parent.cget('bg'), anchor='w', **kw)

    def _layout(self):
        from lotso_scene import rounded
        self.background = tk.Canvas(self.root, bg='#428BCC', highlightthickness=0)
        self.background.pack(fill='both', expand=True)
        def draw_background(event=None):
            c = self.background
            c.delete('decoration')
            w,h = c.winfo_width(),c.winfo_height()
            for x,y,z in [(w-110,78,.42),(w-390,24,.38),(36,h-10,.65),(w-45,h-45,.65)]:
                for dx,dy,rx,ry in [(0,8,26,13),(21,0,24,20),(46,8,27,14)]:
                    c.create_oval(x+(dx-rx)*z,y+(dy-ry)*z,x+(dx+rx)*z,y+(dy+ry)*z,fill='#EAF6FF',outline='',tags='decoration')
            c.create_text(35,49,text='我们将会再见',anchor='w',fill='#204B7C',font=(FONT,-34,'bold'),tags='decoration')
            c.create_text(33,47,text='我们将会再见',anchor='w',fill='#FFDA4F',font=(FONT,-34,'bold'),tags='decoration')
            c.create_line(34,86,108,86,fill='#F8CF49',width=5,tags='decoration')
            c.create_line(112,86,137,86,fill='#DB4B3E',width=5,tags='decoration')
            from toy_header import draw_toys
            draw_toys(c,w)
            rounded(c,23,116,w-21,h-18,22,fill='#2D70AF',outline='',tags='decoration')
            rounded(c,20,111,w-24,h-23,22,fill='white',outline='',tags='decoration')
            c.tag_lower('decoration')
        self.background.bind('<Configure>',draw_background)
        panel=tk.Frame(self.background,bg='white')
        panel.place(x=34,y=126,relwidth=1,width=-82,relheight=1,height=-170)
        panel.grid_columnconfigure(1,weight=1)
        panel.grid_rowconfigure(0,weight=1)
        self.hero=tk.Canvas(panel,width=294,bg='white',highlightthickness=0)
        self.hero.grid(row=0,column=0,sticky='ns')
        self.scene=LotsoScene(self.hero,self.animation.get)
        self.hero.bind('<Configure>',self.draw_hero)
        main=tk.Frame(panel,bg='white',padx=22,pady=4)
        main.grid(row=0,column=1,sticky='nsew')
        main.grid_columnconfigure(0,weight=1)
        cards=tk.Frame(main,bg='white')
        cards.grid(row=0,sticky='ew',pady=(0,10))
        cards.grid_columnconfigure((0,1),weight=1,uniform='service')
        modes=tk.Frame(cards,bg='white')
        modes.grid(row=0,column=0,columnspan=2,sticky='ew',pady=(0,9))
        for value,text in [('wired','有线'),('wireless','无线 · ECJTU-Stu')]:
            tk.Radiobutton(modes,text=text,value=value,variable=self.transport,
                command=lambda:self.select_service(self.service.get()),font=(FONT,-14),
                bg='white',fg=INK,activebackground='white',selectcolor='white',
                bd=0,highlightthickness=0).pack(side='left',padx=(0,20))
        for i,(key,(name,detail,_)) in enumerate(self.app.SERVICES.items()):
            card=tk.Frame(cards,bg='white',highlightbackground=LINE,highlightthickness=1,height=49,cursor='hand2')
            card.grid(row=1+i//2,column=i%2,sticky='ew',padx=(0,5) if i%2==0 else (5,0),pady=(0,8))
            card.grid_propagate(False)
            dot=self.label(card,'○',20,MUTED)
            dot.grid(row=0,column=0,padx=(12,9),pady=10)
            title=self.label(card,name,15,INK,True)
            title.grid(row=0,column=1,sticky='w')
            sub=self.label(card,'',11,MUTED)
            for widget in (card,dot,title):
                widget.bind('<Button-1>',lambda e,k=key:self.select_service(k))
            self.cards[key]=(card,dot,title,sub)
        # Keep contextual descriptions in help, not on the clean main screen.
        self.service_hint=self.label(main,'')
        self.label(main,'学号 / 账号',15,INK,True).grid(row=1,sticky='w',pady=(0,7))
        self.username=self.entry(main)
        self.username.master.grid(row=2,sticky='ew')
        password_head=tk.Frame(main,bg='white')
        password_head.grid(row=3,sticky='ew',pady=(13,7))
        self.password_label=self.label(password_head,'密码',15,INK,True)
        self.password_label.pack(side='left')
        tk.Checkbutton(password_head,text='显示',variable=self.reveal,command=lambda:self.password.config(show='' if self.reveal.get() else '●'),font=(FONT,-13),bg='white',fg=MUTED,activebackground='white',selectcolor='white',bd=0,highlightthickness=0).pack(side='right')
        self.password=self.entry(main,secret=True)
        self.password.master.grid(row=4,sticky='ew')
        self.password_note=self.label(main,'')
        options=tk.Frame(main,bg='white')
        options.grid(row=5,sticky='ew',pady=(12,14))
        for text,variable in [('开机运行',self.autostart),('断线重连',self.reconnect),('动画',self.animation)]:
            tk.Checkbutton(options,text=text,variable=variable,command=self.scene.draw,font=(FONT,-14),bg='white',fg=INK,activebackground='white',selectcolor='white',bd=0,highlightthickness=0).pack(side='left',padx=(0,18))
        buttons=tk.Frame(main,bg='white')
        buttons.grid(row=6,sticky='ew')
        buttons.grid_columnconfigure(0,weight=1)
        self.connect_button=SoftButton(buttons,text='保存并连接  →',command=self.save,bg='#FFD24B',fg=INK,activebackground='#F3C238',font=(FONT,-16,'bold'))
        self.connect_button.grid(row=0,column=0,sticky='ew')
        self.stop_button=tk.Button(buttons,text='停用',command=self.disable,bg='#EAF0F7',fg=INK,activebackground=LINE,font=(FONT,-14),bd=0,padx=22,pady=13,cursor='hand2')
        self.stop_button.grid(row=0,column=1,padx=(12,0))
        state=tk.Frame(main,bg='white')
        state.grid(row=7,sticky='ew',pady=(10,0))
        self.status_dot=self.label(state,'●',12,MUTED)
        self.status_dot.pack(side='left',padx=(0,8))
        self.status=self.label(state,'待连接',13,MUTED,wraplength=455)
        self.status.pack(side='left')
        help_button=tk.Button(self.background,text='?',command=self.help,font=(FONT,-16,'bold'),fg='#214E83',bg='#EAF6FF',activebackground='white',bd=0,width=2,cursor='hand2')
        help_button.place(relx=1,x=-47,y=40,anchor='ne')

    def entry(self, parent, secret=False):
        frame = tk.Frame(parent, bg='white', highlightthickness=1, highlightbackground=LINE)
        field = tk.Entry(frame, font=(FONT, -16), fg=INK, bg='white', relief='flat',
                         insertbackground=TEAL, show='●' if secret else '')
        field.pack(fill='x', padx=12, pady=8)
        field.bind('<FocusIn>', lambda e: frame.config(highlightbackground=TEAL))
        field.bind('<FocusOut>', lambda e: frame.config(highlightbackground=LINE))
        return field

    def draw_hero(self, event=None):
        self.scene.draw()

    def select_service(self, key):
        if self.busy:
            if self.current_profile:
                self.transport.set(self.current_profile.split(':')[0])
            return
        new_profile = self.transport.get() + ':' + key
        if self.current_profile != new_profile:
            if self.current_profile:
                self.drafts[self.current_profile] = dict(username=self.username.get(), password=self.password.get())
            self.current_profile = new_profile
            stored = self.profiles.get(new_profile, {})
            draft = self.drafts.get(new_profile, dict(username=stored.get('username',''),password=''))
            self.username.delete(0,'end')
            self.username.insert(0,draft['username'])
            self.password.delete(0,'end')
            self.password.insert(0,draft['password'])
            self.reveal.set(False)
            self.password.config(show='●')
            self.password_label.config(text='密码（已保存）' if stored.get('password') else '密码')
        self.service.set(key)
        for choice, (card, dot, title, sub) in self.cards.items():
            selected = choice == key
            color = '#EAF3FF' if selected else 'white'
            card.config(bg=color, highlightbackground=TEAL if selected else LINE)
            for widget in (dot, title, sub):
                widget.config(bg=color)
            dot.config(text='●' if selected else '○', fg=TEAL if selected else '#A2B3C6')
            title.config(fg=TEAL if selected else INK)
        self.service_hint.config(text='学校工位网 / 免费校园网：直接使用学号和密码。' if key == 'campus'
                                 else self.app.SERVICES[key][0] + '：使用已开通对应服务的校园网账号。')

    def show_status(self, text, success=False):
        self.status.config(text=text, fg=TEAL if success else MUTED)
        self.status_dot.config(fg=TEAL if success else MUTED)

    def run_async(self, operation, done):
        self.busy = True
        self.connect_button.config(state='disabled', text='正在处理…')
        self.stop_button.config(state='disabled')
        def task():
            try:
                operation()
                self.events.put(('ok', done))
            except Exception as exc:
                self.events.put(('error', type(exc).__name__))
        threading.Thread(target=task, daemon=True).start()

    def save(self):
        if self.preview:
            return
        user, key = self.username.get().strip(), self.service.get()
        try:
            account = self.app.account_for_service(user, key)
            suffix = self.app.SERVICES[key][2]
            user = account[:-len(suffix)] if suffix else account
        except ValueError as exc:
            messagebox.showwarning('检查账号', str(exc), parent=self.root)
            return
        password = self.password.get()
        stored = self.profiles.get(self.current_profile, {})
        old_user = stored.get('username', '')
        try:
            same_account = self.app.account_for_service(old_user, key) == account
        except ValueError:
            same_account = False
        if not password and same_account:
            password = stored.get('password', '')
        if not password:
            messagebox.showwarning('还差一步', '请填写校园网密码。', parent=self.root)
            return
        profiles = dict(self.profiles)
        profiles[self.current_profile] = dict(username=user,password=password)
        preferred_services = dict(self.saved.get('preferred_services', {}))
        preferred_services[self.transport.get()] = key
        config = dict(username=user, password=password, service=key,
                      wired_operator=key if self.transport.get()=='wired' and key!='campus' else self.saved.get('wired_operator'),
                      preferred_services=preferred_services,
                      transport=self.transport.get(), profiles=profiles,
                      autostart=self.autostart.get(), reconnect=self.reconnect.get(),
                      animation=self.animation.get(), schema=4)
        self.show_status('正在保存设置，等待原后台任务结束…')
        def done():
            self.saved = config
            self.profiles = profiles
            self.drafts.pop(self.current_profile, None)
            self.password.delete(0, 'end')
            self.password_label.config(text='密码（已保存）')
            self.show_status('已单独保存，正在检测网络和认证状态。')
        self.run_async(lambda: self.app.save_configuration(config), done)

    def disable(self):
        if self.preview:
            return
        def operation():
            self.app.stop_worker()
            self.app.STARTUP.unlink(missing_ok=True)
        def done():
            self.saved = {}
            self.profiles = {}
            self.drafts = {}
            self.password.delete(0, 'end')
            self.password_label.config(text='密码')
            self.show_status('已停用，保存的账号和启动项已清除。')
        self.show_status('正在停止后台任务…')
        self.run_async(operation, done)

    def poll(self):
        try:
            kind, payload = self.events.get_nowait()
            self.busy = False
            self.connect_button.config(state='normal', text='保存并连接  →')
            self.stop_button.config(state='normal')
            if kind == 'ok':
                payload()
            else:
                self.show_status('设置未完成，请稍后重试。')
                messagebox.showerror('未完成', '操作未完成，请稍后重试。\n如后台正在结束请求，请等待或重新登录 Windows。', parent=self.root)
        except queue.Empty:
            pass
        if not self.busy and not self.preview and self.app.CONFIG.exists() and self.app.STATE.exists():
            try:
                data = json.loads(self.app.STATE.read_text(encoding='utf-8'))
                fresh = time.time() - data.get('epoch', 0) < 660
                if fresh:
                    code = data['state']
                    self.show_status(self.app.LABELS.get(code, code), code in ('online', 'completed'))
                elif data.get('state') == 'completed':
                    self.show_status('上次认证已完成 · 自动重连已关闭')
            except (OSError, ValueError, KeyError):
                pass
        self.root.after(600, self.poll)

    def help(self):
        messagebox.showinfo('使用帮助',
            '学校校园网：免费服务，仅需学号和密码。\n'
            '电信 / 移动 / 联通：请选择已开通的服务。\n\n'
            '开机自动运行：登录 Windows 桌面后自动启动。\n'
            '断线自动重连：持续检测所选网络；关闭后认证成功即退出后台。\n\n'
            '无线：先在 Windows 连接 ECJTU-Stu 并勾选自动连接。\n'
            '有线与无线、四种服务分别保存密码；每项填写后点保存。\n'
            '连接方式失效后自动切换；两种方式需分别保存账号。\n'
            '有线先试已保存的学校免费网，再试已保存的运营商。\n'
            '两种都连接时优先使用最后保存的方式。\n\n'
            '保存后可关闭窗口，后台任务继续运行。\n'
            '连续认证失败会暂停；重新保存可再次尝试。\n'
            '首次使用需在学校网络实测。停用将清除所有模块的账号。', parent=self.root)

    def run(self):
        self.root.mainloop()

    def close(self):
        if self.busy:
            self.show_status('设置正在保存，请完成后再关闭窗口。')
        else:
            self.root.destroy()
