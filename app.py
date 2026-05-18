import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
import threading
import tkinter.font as tkfont
import requests
from bs4 import BeautifulSoup
import json
import os
import sys
import winreg
import winsound
from win10toast import ToastNotifier
from PIL import Image
import pystray
from datetime import datetime

try:
    import keyring
    KEYRING_AVAILABLE = True
except Exception:
    KEYRING_AVAILABLE = False

#jdevrais mettre un systeme pour voir les notes mais plus beau parce que azz c moche l'interface
#aussi pour la notif mettre un bouton pour ouvrir le l'app direct et mettre surout des infos en plus
#et aussi mettre un bouton pour config notre propre son de notif
#a voir




#config persistance
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".formadep_config.json")
APP_NAME = "Formadep Notes"
APP_KEY = "FormadepChecker"



def load_config():
    defaults = {
        "email": "",
        "password": "",
        # Ne pas sauvegarder le mot de passe par défaut pour éviter fuite
        "save_password": False,
        "interval_min": 5,
        "start_minimized": False,
        "autostart": True,
    }
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            defaults.update(data)
    except Exception:
        pass
    # si l'utilisateur a demandé sauvegarde sécurisée et que keyring est dispo,
    # récupérer le mot de passe depuis le porte-clés
    try:
        if defaults.get("save_password") and KEYRING_AVAILABLE and defaults.get("email"):
            pw = keyring.get_password(APP_NAME, defaults.get("email"))
            defaults["password"] = pw or ""
        else:
            # ne pas pré-remplir par défaut
            defaults["password"] = defaults.get("password", "") or ""
    except Exception:
        defaults["password"] = defaults.get("password", "") or ""
    return defaults
def save_config(cfg):
    try:
        # Ne jamais écrire le mot de passe en clair dans le fichier de config
        to_write = dict(cfg)
        if "password" in to_write:
            del to_write["password"]
        with open(CONFIG_FILE, "w") as f:
            json.dump(to_write, f, indent=2)
    except Exception:
        pass

#on config l'autostart windows
def set_autostart(enable: bool):
    exe = sys.executable if getattr(sys, "frozen", False) else f'"{sys.executable}" "{os.path.abspath(__file__)}"'
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, APP_KEY, 0, winreg.REG_SZ, exe)
        else:
            try:
                winreg.DeleteValue(key, APP_KEY)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Autostart error: {e}")

#le scraper
class FormadepScraper:
    BASE = "https://www.formadep360.fr"
    LOGIN_URL = BASE + "/Extra/"
    NOTES_URL = BASE + "/extra/extra_now"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "Origin": self.BASE,
            "Referer": self.LOGIN_URL,
        })
        self.connecte = False




    def login(self, email: str, password: str) -> tuple[bool, str]:
        try:
            #on demande la page de login en premier
            r = self.session.get(self.LOGIN_URL, timeout=15)
            r.raise_for_status()

            #jrecupere les données caché de la page de co
            soup = BeautifulSoup(r.text, "html.parser")
            payload = {}
            for inp in soup.find_all("input", {"type": "hidden"}):
                if inp.get("name"):
                    payload[inp["name"]] = inp.get("value", "")

            #j'ai vu les noms des champs avec devtools dans l'onglet request
            payload["txtnom"] = email
            payload["txtpwd"] = password
            payload["bnconnexion"] = "CONNEXION"
            payload["tbenvoi"] = ""

            r2 = self.session.post(self.LOGIN_URL, data=payload,
                                   timeout=15, allow_redirects=True)
            #si on est redirigé vers extra_now c'est bon
            if "extra_now" in r2.url.lower() or "extra_now" in r2.text.lower():
                self.connecte = True
                return True, "Connecté ✓"
            #sinon on cherche un message d'erreur sur la page
            soup2 = BeautifulSoup(r2.text, "html.parser")
            err = soup2.find(class_=lambda c: c and "error" in c.lower())
            msg = err.get_text(strip=True) if err else "Identifiants incorrects"
            return False, msg
        except requests.RequestException as e:
            return False, f"Erreur réseau : {e}"




    def get_notes(self) -> tuple[list[dict], str]:
        """Returns list of notes dicts and raw hash string for change detection."""
        try:
            r = self.session.get(self.NOTES_URL, timeout=15)
            if r.status_code == 302 or "Extra/" in r.url:
                self.connecte = False
                return [], "SESSION_EXPIRED"
            soup = BeautifulSoup(r.text, "html.parser")
            # je cherche le tableau de note (update un peu plus robuste : on cible d'abord les tables
            # qui ont explicitement note/contrôle/coefficient dans les entêtes vu que la derniere version
            # ne prenait pas ça en compte on avait les emplois du temps)
            notes = []
            table = None
            header_texts = []
            for t in soup.find_all("table"):
                ths = [th.get_text(strip=True).lower() for th in t.find_all("th")]
                # priorité aux tables contenant clairement des colonnes de notes
                if any("note" in h or "contr" in h or "coefficient" in h or "coef" in h for h in ths):
                    table = t
                    header_texts = ths
                    break
            # fallback si pas trouvé chercher des éléments spécifiques générés côté serveur
            if table is None:
                #on cherche des ids comme ListeNotes_labelA_0 qui indiquent la table des notes
                note_marker = soup.find(id=lambda v: v and str(v).lower().startswith("listenotes_"))
                if not note_marker:
                    note_marker = soup.find(id=lambda v: v and str(v).lower().startswith("listenotes_label"))
                if note_marker:
                    table = note_marker.find_parent("table")
                    if table:
                        header_texts = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            # autre fallback si toujours rien, chercher 'ressource' (mais moins fiable)
            if table is None:
                for t in soup.find_all("table"):
                    ths = [th.get_text(strip=True).lower() for th in t.find_all("th")]
                    if any("ressource" in h or "ressources" in h for h in ths):
                        table = t
                        header_texts = ths
                        break
            if table:
                # construire un mapping header to index pour être tolérant aux permutations
                idx = {}
                for i, h in enumerate(header_texts):
                    if "ressource" in h or "ressources" in h or "matiere" in h or "libelle" in h:
                        idx["ressource"] = i
                    elif "controle" in h or "contrôle" in h or "evaluation" in h:
                        idx["controle"] = i
                    elif "coef" in h or "coefficient" in h:
                        idx["coef"] = i
                    elif "note" in h or "moy" in h:
                        idx["note"] = i

                for row in table.find_all("tr")[1:]:  # sauter l'entête
                    cols = [td.get_text(strip=True) for td in row.find_all("td")]
                    if not cols:
                        continue
                    # récupérer en se basant sur les index trouvés sinon fallback par position
                    def get_col(key, fallback_pos):
                        if key in idx and idx[key] < len(cols):
                            return cols[idx[key]]
                        return cols[fallback_pos] if fallback_pos < len(cols) else ""

                    res = get_col("ressource", 0)
                    controle = get_col("controle", 1)
                    coef = get_col("coef", 2)
                    note = get_col("note", 3)
                    notes.append({"ressource": res, "controle": controle, "coef": coef, "note": note})

            raw = "|".join(f"{n['ressource']}{n['controle']}{n['note']}" for n in notes)
            return notes, raw
        except requests.RequestException as e:
            return [], f"ERREUR:{e}"


# l'ui
class FormadepApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.scrapeur = FormadepScraper()
        self.last_hash = None
        self.toaster = ToastNotifier()
        self.check_job = None
        self.tray_icon = None
        self.tray_thread = None
        self._checking = False
        self._setup_window()
        self._build_ui()
        self._apply_config()
        if self.cfg.get("autostart"):
            set_autostart(True)
        # si on a stocké le mot de passe dans le porte-clés on le récupére
        try:
            stored_pwd = ""
            if self.cfg.get("save_password") and KEYRING_AVAILABLE and self.cfg.get("email"):
                stored_pwd = keyring.get_password(APP_NAME, self.cfg.get("email") ) or ""
            if self.cfg.get("email") and stored_pwd:
                self.cfg["password"] = stored_pwd
                self.after(1000, self._start_monitoring)
        except Exception:
            pass

    #setup fenetre
    def _setup_window(self):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        #forcer une police système qui gère bien les caractères accentués (ç, é...)
        try:
            for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont"):
                try:
                    f = tkfont.nametofont(name)
                    f.configure(family="Segoe UI")
                except Exception:
                    pass
        except Exception:
            pass
        self.title(APP_NAME)
        self.geometry("480x620")
        self.resizable(False, False)
        #le fond de l'app
        try:
            self.configure(fg_color="#e8e8e8")
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        #centre la fenêtre
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 480) // 2
        y = (self.winfo_screenheight() - 620) // 2
        self.geometry(f"+{x}+{y}")

    def _build_ui(self):
        #entete logo et status
        header = ctk.CTkFrame(self, fg_color="#1d2124", corner_radius=0)
        header.pack(fill="x")
        #j'essaye d'afficher le logo si sa marche pas jmet un titre
        try:
            img_path = os.path.join(os.path.dirname(__file__), "icon.png")
            logo_pil = Image.open(img_path)
            self.logo_image = ctk.CTkImage(logo_pil, size=(36, 36))
            ctk.CTkLabel(header, image=self.logo_image, text="").pack(side="left", padx=12, pady=10)
        except Exception:
            ctk.CTkLabel(header, text="Formadep Notes", font=ctk.CTkFont(size=20, weight="bold"),
                         text_color="#d1d2d2").pack(side="left", padx=20, pady=14)
        self.status_dot = ctk.CTkLabel(header, text="●", font=ctk.CTkFont(size=18),
                           text_color="#d1d2d2")
        self.status_dot.pack(side="right", padx=20)
        self.status_label = ctk.CTkLabel(header, text="Non connecté",
                         font=ctk.CTkFont(size=12), text_color="#d1d2d2")
        self.status_label.pack(side="right", padx=4)

        # les identifiants 
        cred_frame = ctk.CTkFrame(self, corner_radius=12)
        cred_frame.pack(fill="x", padx=16, pady=(12, 6))
        ctk.CTkLabel(cred_frame, text="Identifiants ENT", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=14, pady=(10, 4))
        self.courriel = ctk.StringVar()
        self.mdp = ctk.StringVar()
        ctk.CTkEntry(cred_frame, placeholder_text="Email", textvariable=self.courriel,
                     width=420).pack(padx=14, pady=4)
        ctk.CTkEntry(cred_frame, placeholder_text="Mot de passe", textvariable=self.mdp,
                     show="*", width=420).pack(padx=14, pady=(4, 10))
        #option pour mémoriser le mot de passe (utilise keyring si dispo)
        self.sauvegarder_mdp = tk.BooleanVar(value=False)
        try:
            ctk.CTkCheckBox(cred_frame, text="Se souvenir du mot de passe",
                    variable=self.sauvegarder_mdp).pack(anchor="w", padx=14, pady=(0,10))
        except Exception:
            pass

        #les parametres
        set_frame = ctk.CTkFrame(self, corner_radius=12)
        set_frame.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(set_frame, text="Paramètres", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=14, pady=(10, 4))

        row1 = ctk.CTkFrame(set_frame, fg_color="transparent")
        row1.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(row1, text="Vérifier toutes les", width=160, anchor="w").pack(side="left")
        self.intervalle_min = tk.IntVar(value=5)
        ctk.CTkSlider(row1, from_=1, to=30, number_of_steps=29, variable=self.intervalle_min,
                  command=lambda v: self.affich_intervalle.configure(text=f"{int(v)} min"),
                  width=160).pack(side="left", padx=8)
        self.affich_intervalle = ctk.CTkLabel(row1, text="5 min", width=50)
        self.affich_intervalle.pack(side="left")

        row2 = ctk.CTkFrame(set_frame, fg_color="transparent")
        row2.pack(fill="x", padx=14, pady=(4, 10))
        self.demarrage_auto = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(row2, text="Lancer au démarrage Windows",
                variable=self.demarrage_auto).pack(side="left")

        #bouton d'action comme demarrer arreter et masquer
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=6)
        self.btn_demarrer = ctk.CTkButton(btn_frame, text="▶  Démarrer",
                           command=self._start_monitoring, width=200,
                           fg_color="#336699", hover_color="#2a5880")
        self.btn_demarrer.pack(side="left", padx=(0, 8))
        self.btn_arreter = ctk.CTkButton(btn_frame, text="⏹  Arrêter",
                          command=self._stop_monitoring, width=120,
                          fg_color="#374151", hover_color="#1f2937",
                          state="disabled")
        self.btn_arreter.pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_frame, text="🔽 Masquer",
                      command=self._hide_to_tray, width=110,
                      fg_color="#374151", hover_color="#1f2937").pack(side="left")

        #le tableau de notes
        cadre_notes = ctk.CTkFrame(self, corner_radius=12)
        cadre_notes.pack(fill="both", expand=True, padx=16, pady=(6, 10))
        ctk.CTkLabel(cadre_notes, text="Dernières notes", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=14, pady=(10, 6))

        cols = ("Ressource", "Contrôle", "Coef.", "Note")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.Treeview", background="#2b2b2b", foreground="#000000",
                fieldbackground="#2b2b2b", rowheight=26, font=("Segoe UI", 10))
        style.configure("Dark.Treeview.Heading", background="#336699", foreground="#ffffff",
                font=("Segoe UI", 10, "bold"), relief="flat", borderwidth=0)
        style.map("Dark.Treeview", background=[("selected", "#2563eb")])

        self.table_notes = ttk.Treeview(cadre_notes, columns=cols, show="headings",
                     style="Dark.Treeview", height=8)
        self.table_notes.heading("Ressource", text="Ressource")
        self.table_notes.heading("Contrôle", text="Contrôle")
        self.table_notes.heading("Coef.", text="Coef.")
        self.table_notes.heading("Note", text="Note")
        self.table_notes.column("Ressource", width=220, anchor="w")
        self.table_notes.column("Contrôle", width=90, anchor="center")
        self.table_notes.column("Coef.", width=60, anchor="center")
        self.table_notes.column("Note", width=70, anchor="center")
        self.table_notes.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        #rayure des tableau 1/2
        try:
            self.table_notes.tag_configure('even', background='#e8e8e8', foreground='#000000')
            self.table_notes.tag_configure('odd', background='#dcdcdc', foreground='#000000')
        except Exception:
            pass

        #le footer avec la date de la derniere verif
        self.dernier_check = ctk.CTkLabel(self, text="Dernière vérification : —",
                              font=ctk.CTkFont(size=11), text_color="#555")
        self.dernier_check.pack(pady=(0, 8))

    def _apply_config(self):
        self.courriel.set(self.cfg.get("email", ""))
        # ne pas charger automatiquement le mot de passe dans l'UI !
        # (sa évite de pré-remplir avec un mot de passe sauvegardé par erreur)
        self.mdp.set("")
        self.intervalle_min.set(self.cfg.get("interval_min", 5))
        self.affich_intervalle.configure(text=f"{self.cfg.get('interval_min', 5)} min")
        self.demarrage_auto.set(self.cfg.get("autostart", True))
        #état de la case "se souvenir"
        try:
            self.sauvegarder_mdp.set(self.cfg.get("save_password", False))
        except Exception:
            pass

    #pour la surveillance des notes
    def _save_and_login(self):
        email = self.courriel.get().strip()
        pwd = self.mdp.get().strip()
        if not email or not pwd:
            messagebox.showwarning(APP_NAME, "Remplis l'email et le mot de passe.")
            return False
        self._set_status("Connexion...", "#f59e0b")
        ok, msg = self.scrapeur.login(email, pwd)
        if ok:
            self._set_status("Connecté ✓", "#22c55e")
            #on n'enregistre pas le mot de passe sauf si l'utilisateur a explicitement demandé
            to_save = {"email": email,
                       "interval_min": self.intervalle_min.get(),
                       "autostart": self.demarrage_auto.get(),
                       "save_password": bool(self.sauvegarder_mdp.get())}

            #gérer le stockage sécurisé via keyring si demandé
            try:
                if self.sauvegarder_mdp.get() and KEYRING_AVAILABLE:
                    keyring.set_password(APP_NAME, email, pwd)
                else:
                    if KEYRING_AVAILABLE:
                        try:
                            keyring.delete_password(APP_NAME, email)
                        except Exception:
                            pass
            except Exception:
                pass

            #ne pas écrire le mot de passe en clair dans le fichier de config
            self.cfg.update(to_save)
            save_config(self.cfg)
            set_autostart(self.demarrage_auto.get())
            return True
        else:
            self._set_status(f"Erreur : {msg}", "#ef4444")
            return False

    def _start_monitoring(self):
        if self._checking:
            return
        if not self.scrapeur.connecte:
            if not self._save_and_login():
                return
        self._checking = True
        self.btn_demarrer.configure(state="disabled")
        self.btn_arreter.configure(state="normal")
        self._check_now()

    def _stop_monitoring(self):
        self._checking = False
        if self.check_job:
            self.after_cancel(self.check_job)
            self.check_job = None
        self.btn_demarrer.configure(state="normal")
        self.btn_arreter.configure(state="disabled")
        self._set_status("Surveillance arrêtée", "#888")

    def _check_now(self):
        if not self._checking:
            return

        def worker():
            if not self.scrapeur.connecte:
                # on récupére le mot de passe depuis la config ou keyring au besoin
                pw = self.cfg.get("password", "")
                if not pw and KEYRING_AVAILABLE and self.cfg.get("email"):
                    try:
                        pw = keyring.get_password(APP_NAME, self.cfg.get("email")) or ""
                    except Exception:
                        pw = ""
                ok, msg = self.scrapeur.login(self.cfg["email"], pw)
                if not ok:
                    self.after(0, lambda: self._set_status(f"Reconnexion échouée : {msg}", "#ef4444"))
                    self._schedule_next()
                    return

            notes, raw = self.scrapeur.get_notes()
            if raw == "SESSION_EXPIRED":
                #si session périmée, on marque déco et on re-planifie
                self.scrapeur.connecte = False
                self._schedule_next()
                return

            if raw.startswith("ERREUR"):
                #pour erreur réseau ou autre on l'affiche et on continue
                self.after(0, lambda: self._set_status(f"⚠ {raw}", "#f59e0b"))
                self._schedule_next()
                return

            new_note_found = self.last_hash is not None and raw != self.last_hash
            self.last_hash = raw

            now = datetime.now().strftime("%H:%M:%S")
            self.after(0, lambda: self._update_table(notes, now, new_note_found))

        threading.Thread(target=worker, daemon=True).start()

    def _schedule_next(self):
        if self._checking:
            interval_ms = self.intervalle_min.get() * 60 * 1000
            self.check_job = self.after(interval_ms, self._check_now)

    def _update_table(self, notes, timestamp, new_note_found):
        for row in self.table_notes.get_children():
            self.table_notes.delete(row)
        for i, n in enumerate(notes):
            tag = 'even' if i % 2 == 0 else 'odd'
            self.table_notes.insert("", "end", values=(n["ressource"], n["controle"], n["coef"], n["note"]), tags=(tag,))
        self.dernier_check.configure(text=f"Dernière vérification : {timestamp}")
        self._set_status("Surveillance activée ✓", "#22c55e")
        if new_note_found:
            self._alert_new_note()
        self._schedule_next()

    def _alert_new_note(self):
        #alerte nouvelle note son, notif et flash
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass
        # pr notif windows
        try:
            self.toaster.show_toast(
                "📚 Nouvelle note !",
                "Une nouvelle note est disponible sur Formadep.",
                duration=6,
                threaded=True,
            )
        except Exception:
            pass
        # on fait "ding" ou flash si la fenêtre est visible
        try:
            self.bell()
        except Exception:
            pass

    def _set_status(self, text, color):
        self.status_label.configure(text=text)
        self.status_dot.configure(text_color=color)

    #l'icône dans la zone de notif(tray)
    def _hide_to_tray(self):
        self.withdraw()
        self._create_tray()

    def _create_tray(self):
        if self.tray_icon:
            return
        #on fait une icon simple en vite fait si sa foire
        try:
            img = Image.open(os.path.join(os.path.dirname(__file__), "icon.png"))
        except Exception:
            img = Image.new("RGB", (64, 64), color=(37, 99, 235))

        menu = pystray.Menu(
            pystray.MenuItem("Afficher", self._show_from_tray, default=True),
            pystray.MenuItem("Vérifier maintenant", lambda: threading.Thread(target=self._check_now, daemon=True).start()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quitter", self._quit_app),
        )
        self.tray_icon = pystray.Icon(APP_KEY, img, APP_NAME, menu)
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()

    def _show_from_tray(self):
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        self.after(0, self.deiconify)

    def _on_close(self):
        self._hide_to_tray()

    def _quit_app(self):
        self._stop_monitoring()
        if self.tray_icon:
            self.tray_icon.stop()
        self.after(0, self.destroy)


#pour lancer l'app
if __name__ == "__main__":
    app = FormadepApp()
    app.mainloop()
