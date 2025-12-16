import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import json
import asyncio
from flask import Flask
from threading import Thread

# --- CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# --- GESTION DES DONNÉES ---
SAVE_FILE = "gamedata.json"

def load_data():
    # 1. Initialiser toutes les variables à leur état par défaut (vide)
    catalogue, inventaires, catalogue_pouvoirs, catalogue_equipements, catalogue_ennemis, catalogue_personnages_1v1   = {}, {}, {}, {}, {}, {}

    # 2. Essayer de charger le fichier de sauvegarde principal (gamedata.json)
    try:
        with open(SAVE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            inventaires = {int(k): v for k, v in data.get("inventaires", {}).items()}
            catalogue = data.get("catalogue", {})
            catalogue_pouvoirs = data.get("catalogue_pouvoirs", {})
            catalogue_equipements = data.get("catalogue_equipements", {})
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Avertissement : Fichier de sauvegarde '{SAVE_FILE}' non trouvé ou corrompu. De nouvelles données seront créées.")
        # Pas besoin de faire plus, les variables sont déjà des dictionnaires vides.

    # 3. Essayer de charger le catalogue d'ennemis (de manière indépendante)
    try:
        with open("catalogue_ennemis.json", 'r', encoding='utf-8') as f:
            catalogue_ennemis = json.load(f)
        print("Clés du catalogue ennemis chargées :", catalogue_ennemis.keys())
    except (FileNotFoundError, json.JSONDecodeError):
        print("ERREUR CRITIQUE : Fichier 'catalogue_ennemis.json' non trouvé ou corrompu. Le catalogue des ennemis sera vide.")
        # catalogue_ennemis reste un dictionnaire vide.
        
    print("Tentative de chargement du fichier 'catalogue_personnages_1v1.json'...")
    try:        
        with open("catalogue_personnages_1v1.json", 'r', encoding='utf-8') as f:            
            catalogue_personnages_1v1 = json.load(f)        
            print("Clés du catalogue 1v1 chargées :", catalogue_personnages_1v1.keys())    
    except (FileNotFoundError, json.JSONDecodeError):        
        print("ERREUR CRITIQUE : Fichier 'catalogue_personnages_1v1.json' non trouvé ou corrompu. Le catalogue sera vide.")        
        # catalogue_personnages_1v1 reste un dictionnaire vide.

    # 4. Retourner les 5 variables, qui sont maintenant garanties d'exister.
    return catalogue, inventaires, catalogue_pouvoirs, catalogue_equipements, catalogue_ennemis, catalogue_personnages_1v1

# --- CHARGEMENT DES DONNÉES GLOBALES ---
# Ces variables seront attachées à l'objet 'bot' pour être accessibles depuis les Cogs.
bot.catalogue_personnages, bot.inventaires, bot.catalogue_de_pouvoirs, bot.catalogue_equipements, bot.catalogue_ennemis, bot.catalogue_personnages_1v1 = load_data()

def save_data():
    with open(SAVE_FILE, 'w', encoding='utf-8') as f:
        data_to_save = {
            "catalogue": bot.catalogue_personnages,
            "inventaires": bot.inventaires,
            "catalogue_pouvoirs": bot.catalogue_de_pouvoirs,
            "catalogue_equipements": bot.catalogue_equipements
        }
        json.dump(data_to_save, f, indent=4, ensure_ascii=False)

# Attacher la fonction de sauvegarde au bot pour y accéder depuis les Cogs
bot.save_data = save_data

# --- FONCTIONS UTILITAIRES GLOBALES ---
# Nous les attachons aussi au bot pour qu'elles soient accessibles partout.
def get_user_inventory(user_id):
    user_id = int(user_id)
    if user_id not in bot.inventaires:
        bot.inventaires[user_id] = {"personnages": [], "reserve_combat": [None, None, None], "pouvoirs": []}
    # Vérifications supplémentaires pour les anciennes données
    if "reserve_combat" not in bot.inventaires[user_id]:
        bot.inventaires[user_id]["reserve_combat"] = [None, None, None]
    if "pouvoirs" not in bot.inventaires[user_id]:
        bot.inventaires[user_id]["pouvoirs"] = []
    if "equipements" not in bot.inventaires[user_id]:            
        bot.inventaires[user_id]["equipements"] = []
    return bot.inventaires[user_id]

bot.get_user_inventory = get_user_inventory

# --- ÉVÉNEMENTS DU BOT ---
@bot.event
async def on_ready():
    print(f'{bot.user.name} est connecté à Discord !')
    print("Vérification des combats interrompus...")    
    combat_cog = bot.get_cog('CombatCog')    
    if combat_cog:        
        interrupted_combats = combat_cog._load_all_combat_states()        
        if not interrupted_combats:            
            print("Aucun combat à reprendre.")        
        else:            
            for channel_id, state in interrupted_combats.items():                
                print(f"Reprise du combat dans le canal {channel_id}...")
                # On passe tous les arguments attendus par la fonction, même s'ils sont None,
                # car la logique de reprise se base uniquement sur resumed_state.
                asyncio.create_task(combat_cog.lancer_combat_engine(
                    log_message=None,
                    team_a=None,
                    team_b=None,
                    titre_combat=None,
                    nom_joueur=None,
                    nom_adversaire=None,
                    resumed_state=state
                )) 
    else:        
        print("ATTENTION : Le Cog 'CombatCog' n'a pas été trouvé. Impossible de reprendre les combats.")
    try:
        # La synchronisation se fait ici une fois que tout est chargé
        synced = await bot.tree.sync()
        print(f"Synchronisé {len(synced)} commande(s)")
    except Exception as e:
        print(e)


# --- LISTE DES COGS À IGNORER AU CHARGEMENT ---
# Mettez ici les noms de fichiers des cogs que vous voulez désactiver.
# Parfait pour mettre de côté des fonctionnalités sans les supprimer.
cogs_desactives = [
    "combat.py",  # Vous l'aviez déjà, on le met ici pour tout centraliser
    "gestion.py",    # <--- REMPLACEZ PAR LE VRAI NOM DE FICHIER
    "admin.py",
    "game_manager.py",
    "nouveau.py"# <--- AJOUTEZ TOUS LES COGS DU JEU 1 ICI
]
# --- DÉMARRAGE DU BOT ET CHARGEMENT DES COGS ---
# --- DÉMARRAGE DU BOT ET CHARGEMENT DES COGS ---
async def main():
    async with bot:
        # Boucle pour charger tous les fichiers dans le dossier 'cogs'
        for filename in os.listdir('./cogs'):
            # On vérifie que le fichier est un .py ET qu'il n'est PAS dans notre liste noire
            if filename.endswith('.py') and filename not in cogs_desactives:
                try:
                    await bot.load_extension(f'cogs.{filename[:-3]}')
                    print(f"✅ Cog '{filename}' chargé.")
                except Exception as e:
                    print(f"❌ Erreur lors du chargement du cog '{filename}': {e}")

        await bot.start(TOKEN)
        
app = Flask('')
@app.route('/')
def home():    
    return "Je suis en vie !"
def run_flask():  
    app.run(host='0.0.0.0',port=8080)
def keep_alive():    
    t = Thread(target=run_flask)    
    t.start()

if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)        
    flask_thread.start()
    # Initialisation des pouvoirs par défaut (gardé ici car modifie les données globales avant le lancement)
    if "Frénésie" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Frénésie"] = {"nom": "Frénésie", "description": "Le personnage attaque une fois de plus.", "activation": 45}
    if "Don" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Don"] = {"nom": "Don", "description": "Soigne de 25% des PV max du lanceur un allié en réserve ayant le moins de PV.", "activation": 75}
    if "Le Poulet" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Le Poulet"] = {"nom": "Le Poulet", "description": "Invoque un poulet qui tank les prochains dégâts.", "activation": 50}
    if "Bourbier" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Bourbier"] = {"nom": "Bourbier", "description": "Empêche l'adversaire de jouer son prochain tour.", "activation": 30}
    if "Prescience" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Prescience"] = {"nom": "Prescience", "description": "Inflige des dégâts après 10 tours.", "activation": 25}
    if "Peur bleu" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Peur bleu"] = {"nom": "Peur bleu", "description": "Empêche l'adversaire de changer de personnage à son prochain tour.", "activation": 65}
    if "Rugissement primal" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Rugissement primal"] = {"nom": "Rugissement primal", "description": "Force l'adversaire à changer son personnage actif avec un autre, choisi aléatoirement dans sa réserve.", "activation": 40}
    if "Bouclier magique" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Bouclier magique"] = {"nom": "Bouclier magique", "description": "Protège toute l'équipe des effets et dégâts des pouvoirs adverses jusqu'à votre prochain tour.", "activation": 30}
    if "Combo" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Combo"] = {"nom": "Combo", "description": "Inflige des dégâts basés sur le nombre de pouvoirs activés avant lui ce tour (25%/75%/150%).", "activation": 35}
    if "Bombardement" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Bombardement"] = {"nom": "Bombardement", "description": "Inflige 50% de l'attaque aux adversaires en réserve en ignorant toutes les protections. Le lanceur saute son prochain tour.", "activation": 20}
    if "Pile ou Face" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Pile ou Face"] = {"nom": "Pile ou Face","description": "Lance une pièce : si c'est face, inflige son attaque en dégâts bruts. Si c'est pile, subit son attaque en dégâts bruts.","activation": 25}
    if "Armure" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Armure"] = {"nom": "Armure","description": "Le lanceur obtient 3 points d'armure.","activation": 25}
    if "Batteries d'urgences" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Batteries d'urgences"] = {"nom": "Batteries d'urgences","description": "Le lanceur se soigne de 25% de ses PV max.","activation": 25}
    if "Nécromancie" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Nécromancie"] = {"nom": "Nécromancie","description": "Invoque un zombie qui combat à votre place. Le lanceur devient inactif.","activation": 25}
    if "Bénédiction" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Bénédiction"] = {"nom": "Bénédiction","description": "Soigne tous les personnages vivants et en réserve de 20% des PV max du lanceur.","activation": 25}
    if "Chaos" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Chaos"] = {"nom": "Chaos","description": "Active un pouvoir aléatoire du jeu. Son pourcentage d'activation change à chaque tour.","activation": 0}
    if "Poison" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Poison"] = {"nom": "Poison", "description": "Empoisonne l'adversaire, lui infligeant 1 dégât par charge au début de son tour. Cumulable.", "activation": 30}
    if "Elan de puissance" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Elan de puissance"] = {"nom": "Elan de puissance", "description": "Augmente l'attaque de 5 pendant 5 tours. Réactiver le pouvoir réduit la durée de 1 mais augmente le bonus de 2.", "activation": 20}
    if "Talon d'Achille" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Talon d'Achille"] = {"nom": "Talon d'Achille", "description": "Les prochains dégâts infligés par l'équipe ignorent toutes les défenses (armure, poulets, zombies).", "activation": 55}
    if "Mimétisme" not in bot.catalogue_de_pouvoirs: bot.catalogue_de_pouvoirs["Mimétisme"] = {"nom": "Mimétisme", "description": "Copie le dernier pouvoir activé par l'adversaire.", "activation": 45}
    if "Tempo" not in bot.catalogue_equipements:bot.catalogue_equipements["Tempo"] = {
        "nom": "Tempo",
        "description": "Donne 2 d'armure quand le personnage apparaît et permet de jouer deux fois si aucun dégât n'est subi lors du tour adverse."
    }
    if "Grimoire interdit" not in bot.catalogue_equipements:bot.catalogue_equipements["Grimoire interdit"] = {
        "nom": "Grimoire interdit",
        "description": "Réduit les PV max de 75% et augmente les chances des pouvoirs à 100% pendant 3 tours."
    }
    if "Baguette explosive" not in bot.catalogue_equipements:bot.catalogue_equipements["Baguette explosive"] = {
        "nom": "Baguette explosive",    
        "description": "Donne les statuts 'Coup Critique' et 'Chanceux' à son porteur."
    }
    if "Côte épineuse" not in bot.catalogue_equipements:bot.catalogue_equipements["Côte épineuse"] = {  
        "nom": "Côte épineuse",  
        "description": "Renvoie 50% des dégâts subis à l'attaquant (ne fonctionne pas contre le poison ou le Talon d'Achille)."}
    if "Hachoir" not in bot.catalogue_equipements:bot.catalogue_equipements["Hachoir"] = {  
        "nom": "Hachoir",  
        "description": "Exécute l'ennemi en dessous dee 25% de ses pv max"}
    if "La Couronne" not in bot.catalogue_equipements:bot.catalogue_equipements["La Couronne"] = {  
        "nom": "La Couronne",  
        "description": "La Couronne est unique ! Respectez là comme un trône précieux"}
    if "Bandeau rouge" not in bot.catalogue_equipements:bot.catalogue_equipements["Bandeau rouge"] = {  
        "nom": "Bandeau rouge",  
        "description": "Survit pour un tour lorsqu'il doit mourir"}
    if "Lance-bouclier" not in bot.catalogue_equipements:bot.catalogue_equipements["Lance-bouclier"] = {        
        "nom": "Lance-bouclier",        
        "description": "Donne +5 en attaque de base et +5 aux PV max."}
    if "Cape magique" not in bot.catalogue_equipements:bot.catalogue_equipements["Cape magique"] = {        
        "nom": "Cape magique",        
        "description": "Bloque les 10 prochains pouvoirs adverses visant le porteur. Activer 'Bouclier magique' avec la cape déclenche une attaque bonus."}
    if "Pierre du changement" not in bot.catalogue_equipements:bot.catalogue_equipements["Pierre du changement"] = {        
        "nom": "Pierre du changement",        
        "description": "Chaque fois qu'il quitte le terrain, gagne +1 aux dégâts."}
    
    save_data()    
    print("Catalogues par défaut vérifiés et sauvegardés.")
    keep_alive()
    asyncio.run(main())