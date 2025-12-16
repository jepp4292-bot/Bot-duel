import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import random
import copy
import math

# On importe le Cog de combat pour pouvoir l'utiliser
from .combat import CombatCog

class GameManagerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Dictionnaire pour stocker les états des parties en cours
        # Clé: channel_id, Valeur: dictionnaire de l'état de la partie
        self.active_games = {}


    @app_commands.command(name="aventure_tuto", description="Lance l'aventure tutoriel.")
    async def aventure_tuto(self, interaction: discord.Interaction):
        # 1. Vérification simple
        if interaction.channel.id in self.active_games:
            return await interaction.response.send_message("Une partie est déjà en cours dans ce salon.", ephemeral=True)
        
        # 2. On répond à l'interaction pour que Discord ne la considère pas comme échouée
        await interaction.response.send_message(f"Lancement de l'aventure 'Tutoriel' pour {interaction.user.mention}...")

        # 3. On appelle le chef d'orchestre pour qu'il fasse tout le travail de préparation.
        #    On lance cela en tâche de fond pour ne pas bloquer le bot.
        asyncio.create_task(self._create_and_start_pve_game(interaction, adventure_name="Tutoriel"))



    # DANS cogs/game_manager.py, dans la classe GameManagerCog

    async def _create_and_start_pve_game(self, interaction: discord.Interaction, adventure_name: str):
        """Prépare et lance une nouvelle aventure PvE de A à Z."""
        
        # --- 1. NETTOYAGE (comme en PvP) ---
        user_inv = self.bot.get_user_inventory(interaction.user.id)
        user_inv["pouvoirs"] = []
        user_inv["equipements"] = []
        user_inv["reserve_combat"] = [None, None, None]
        await interaction.user.send("Votre inventaire a été vidé pour cette aventure.")
        self.bot.save_data()

        # --- 2. CRÉATION DE L'ÉTAT DE LA PARTIE ---
        player_state = {
            'member': interaction.user,
            'hp': 20,
            'gold': 200,
            'reserve_combat': [None, None, None], # Commence avec une réserve vide
            'inventory': {'pouvoirs': [], 'equipements': []},
            'is_ready': False,
            'last_reserve_message_id': None,
            'last_inventory_message_id': None
        }

        game_state = {
            'channel_id': interaction.channel.id,
            'player': player_state, # La structure est 'player', pas 'players' comme en PvP
            'current_wave': 0,
            'combat_ready_event': asyncio.Event(),
            'game_mode': 'pve'
        }
        self.active_games[interaction.channel.id] = game_state

        # --- 3. PHASE DE SETUP INITIALE (GRATUITE) ---
        # C'est ici qu'on lance la roulette gratuite et qu'on envoie les inventaires.
        await self._player_setup_phase(player_state, game_state['game_mode'])
        
        # --- 4. LANCEMENT DE LA BOUCLE DE JEU PRINCIPALE ---
        # Maintenant que tout est prêt, on lance la boucle qui gérera les vagues.
        await self.run_pve_loop(game_state, adventure_name)


    async def run_pve_loop(self, game_state, adventure_name: str ):
        """La boucle principale du mode Aventure (PvE)."""
        channel = self.bot.get_channel(game_state['channel_id'])
        combat_cog = self.bot.get_cog('CombatCog')
        player_data = game_state['player']

        # On définit les vagues ici. C'est une liste de listes de noms d'ennemis.
        
        all_adventures = {            
            "Tutoriel": [                
                ["Robot Gardien"],                
                # Tu pourras ajouter d'autres vagues pour le tuto ici   
                ["Robot épée", "Robot bouclier", "Robot mage"],
                ["Dr. Change"],
                ["Blob noir", "Entité 001"],
                ["Dr. Change corrompu"]  
                ]            
           }
        adventure_waves = all_adventures.get(adventure_name, [])
            

        wave_index = 0    
        # On utilise une boucle 'while' pour pouvoir recommencer une vague en cas de défaite.    
        while player_data['hp'] > 0 and wave_index < len(adventure_waves):        
            game_state['current_wave'] = wave_index + 1        
            wave_enemies_names = adventure_waves[wave_index]        
            # --- PHASE DE PRÉPARATION (AVANT CHAQUE VAGUE) ---        
            game_state['combat_ready_event'].clear() # On réinitialise l'événement        
            player_data['is_ready'] = False                
            profil_embed = discord.Embed(title=f"Aventure '{adventure_name}' - Vague {game_state['current_wave']}", color=discord.Color.blue())        
            profil_embed.add_field(name=f"👤 {player_data['member'].display_name}", value=f"❤️ **HP :** {player_data['hp']}\n💰 **Gold :** {player_data['gold']}", inline=True)                
            await channel.send(embed=profil_embed, view=PreparationView(self, game_state))        
            await game_state['combat_ready_event'].wait() # On attend que le joueur clique "Prêt"

            # --- PHASE DE COMBAT ---
            enemy_team = []
            for enemy_name in wave_enemies_names:
                enemy_data = self.bot.catalogue_ennemis.get(enemy_name)
                if enemy_data:
                    enemy_team.append(copy.deepcopy(enemy_data))
            
            if not enemy_team:
                await channel.send(f"Erreur : Impossible de charger les ennemis pour la vague {game_state['current_wave']}.")
                break

            await channel.send(f"🌊 **Vague {game_state['current_wave']} !** Vous affrontez : {', '.join(wave_enemies_names)}.")
            await asyncio.sleep(3)

            log_message = await channel.send(embed=discord.Embed(title="Combat PvE en cours..."))

            # On appelle le moteur de combat
            combat_result = await combat_cog.lancer_combat_engine(
                log_message=log_message,
                team_a=player_data['reserve_combat'],
                team_b=enemy_team,
                titre_combat=f"Aventure - Vague {game_state['current_wave']}",
                nom_joueur=player_data['member'].name,
                nom_adversaire="Ennemis",  # Nom générique pour l'adversaire
                is_pve=True  # Le drapeau pour dire au moteur que c'est du PvE !
            )

            if not combat_result or combat_result.get('winner_id') != player_data['member'].id:
                hp_lost = game_state['current_wave'] * 2  # On perd des PV égaux au numéro de la vague x 2
                player_data['hp'] -= hp_lost
                await channel.send(f"💔 **Défaite !** Vous avez perdu la vague et subissez **{hp_lost}** points de dégâts. Il vous reste {player_data['hp']} HP.")
                player_data['gold'] += 500  # Gain de gold en cas de défaite
                player_data['reserve_combat'] = self._reset_characters_for_next_round(combat_result['team_a_final'])
                await self._send_reserve_view_dm(player_data)
                await self._send_inventories_dm(player_data)
                if player_data['hp'] <= 0:
                    await channel.send("💀 Votre aventure s'arrête ici...")
                    break  # Sort de la boucle for
            else:
                await channel.send(f"🏆 **Victoire !** Vous avez triomphé de la vague {game_state['current_wave']}.")
                player_data['gold'] += 250  # Gain de gold en cas de victoire
                # On réinitialise l'équipe du joueur pour la prochaine vague
                player_data['reserve_combat'] = self._reset_characters_for_next_round(combat_result['team_a_final'])
                wave_index += 1 # On passe à la vague suivante
                await self._send_reserve_view_dm(player_data)
                await self._send_inventories_dm(player_data)

        # Fin de la boucle
        del self.active_games[channel.id]

    
    

    async def _create_and_start_game(self, interaction: discord.Interaction, player1: discord.Member, player2: discord.Member):
        """Fonction centrale qui initialise et lance une partie entre deux joueurs (humain ou bot)."""
        
        # On nettoie l'inventaire de tous les joueurs humains
        for p in [player1, player2]:
            if not p.bot:
                user_inv = self.bot.get_user_inventory(p.id)
                user_inv["pouvoirs"] = []
                user_inv["equipements"] = []
                user_inv["reserve_combat"] = [None, None, None]
                await p.send("Votre inventaire permanent a été vidé pour cette partie.")
        self.bot.save_data()

        combat_cog = self.bot.get_cog('CombatCog')
        
        # Création du dictionnaire pour chaque joueur
        players_dict = {}
        for p in [player1, player2]:
            player_id = p.id if not p.bot else 'bot'
            players_dict[player_id] = {
                'member': p,
                'hp': 10,
                'gold': 0,
                'is_ready': p.bot, # Le bot est toujours prêt
                'inventory': {'pouvoirs': [], 'equipements': []},
                'reserve_combat': combat_cog._creer_equipe_aleatoire() if p.bot else [None, None, None],
                'last_reserve_message_id': None,
                'last_inventory_message_id': None
            }

        game_state = {
            'channel_id': interaction.channel.id,
            'players': players_dict,
            'game_mode': 'pvp'
        }
        self.active_games[interaction.channel.id] = game_state

        # Le message de suivi dépend si c'est une réponse à une interaction de commande ou d'un bouton
        if interaction.response.is_done():
            await interaction.followup.send(f"Nouvelle partie lancée ! {player1.mention} vs {player2.mention}. La partie commence dans 10 secondes...")
        else: # Ce cas ne devrait pas arriver avec la structure actuelle, mais c'est une sécurité
            await interaction.response.send_message(f"Nouvelle partie lancée ! {player1.mention} vs {player2.mention}. La partie commence dans 10 secondes...")


        # Lancer la boucle de jeu principale
        asyncio.create_task(self.run_game_loop(game_state))

    # MODIFIEZ LA COMMANDE /partie_test EXISTANTE

    @app_commands.command(name="partie_test", description="Lance une partie test contre le bot.")
    async def partie_test(self, interaction: discord.Interaction):
        if interaction.channel.id in self.active_games:
            return await interaction.response.send_message("Une partie est déjà en cours dans ce salon.", ephemeral=True)

        # On appelle simplement la fonction centrale avec le bot comme adversaire
        await self._create_and_start_game(interaction, interaction.user, self.bot.user)
            
        
    # AJOUTEZ CETTE NOUVELLE COMMANDE DANS cogs/game_manager.py

    @app_commands.command(name="partie", description="Défie un autre joueur dans une partie.")
    @app_commands.describe(adversaire="Le joueur que vous voulez défier.")
    async def partie(self, interaction: discord.Interaction, adversaire: discord.Member):
        # --- Vérifications initiales ---
        if adversaire.id == interaction.user.id:
            return await interaction.response.send_message("Vous ne pouvez pas vous défier vous-même.", ephemeral=True)
        if adversaire.bot:
            return await interaction.response.send_message("Vous ne pouvez pas défier un bot. Utilisez `/partie_test`.", ephemeral=True)
        if interaction.channel.id in self.active_games:
            return await interaction.response.send_message("Une partie est déjà en cours dans ce salon.", ephemeral=True)

        # --- Envoi de l'invitation ---
        view = InvitationView(self, interaction.user, adversaire)
        await interaction.response.send_message(f"⚔️ {interaction.user.mention} défie {adversaire.mention} ! {adversaire.mention}, vous avez 3 minutes pour répondre.", view=view)
        
        # On attend que l'adversaire clique sur un bouton (ou que le timeout soit atteint)
        await view.wait()

        if view.result is True:
            # L'invitation est acceptée, on lance le processus de création de partie
            await self._create_and_start_game(interaction, interaction.user, adversaire)
        elif view.result is False:
            # L'invitation est refusée, on ne fait rien de plus
            pass
        else:
            # Timeout, personne n'a répondu
            message = await interaction.original_response()
            await message.edit(content="L'invitation a expiré.", view=None)
            
    

    async def start_combat(self, game_state):        
            """Vérifie si tous les joueurs sont prêts et lance le combat si c'est le cas."""        
            # Pour l'instant, on ne vérifie que le joueur humain car le bot est toujours prêt.        
            # # Cette logique pourra être étendue pour plusieurs joueurs humains.                
            all_players = [p for p_id, p in game_state['players'].items() if p_id != 'bot']                
            if all(p['is_ready'] for p in all_players):            
                # On désactive les boutons de la vue de préparation            
                channel = self.bot.get_channel(game_state['channel_id'])            
                # On récupère le dernier message envoyé qui contient la vue            
                async for msg in channel.history(limit=10):                
                    if msg.author == self.bot.user and msg.components:                    
                        await msg.edit(view=None) # Supprime les boutons                    
                        break            # On débloque la boucle de jeu            
                game_state['combat_ready_event'].set()
    
# Dans cogs/game_manager.py, remplace toute la fonction run_game_loop

    # Dans cogs/game_manager.py, à l'intérieur de la classe GameManagerCog

    def _reset_characters_for_next_round(self, team: list) -> list:
        """Réinitialise correctement les stats des personnages survivants pour la manche suivante."""
        for character in team:
            if character and character['pv'] >= 0:
                original_stats = self.bot.catalogue_personnages.get(character['nom'])
                if not original_stats:
                    print(f"AVERTISSEMENT: Personnage '{character['nom']}' non trouvé dans le catalogue.")
                    continue
                
                # 1. Restaurer les stats de base depuis le catalogue
                character['max_pv'] = original_stats['pv']
                character['pv'] = original_stats['pv']
                character['attaque'] = original_stats['attaque']
                character['base_attaque'] = original_stats['attaque']
                
                
                # 3. Nettoyer les statuts de combat
                character['poison_stacks'] = 0
                character['effects'] = []
                character['etats'] = []
                character['armure'] = 0
                character['bandeau_used_this_stint'] = False
                if character.get('nom') == "Le Robot":
                    character['repair_mode_active'] = False
                    character['repair_turns_left'] = 0
                    character['ability_used_this_stint'] = False
                if character.get('nom') == "Le Parieur":
                    character['parieur_ability_ready'] = True
        return team


    async def _player_setup_phase(self, player_data, game_mode):
        """Gère la phase de setup initiale (roulette, etc.) pour un seul joueur."""
        if player_data['member'].bot:
            return

        # --- NOUVELLE LOGIQUE BASÉE SUR LE MODE DE JEU ---

        if game_mode == 'pvp':
            # --- LOGIQUE POUR LE DUEL PVP RAPIDE ---
            await player_data['member'].send("Début de la phase de préparation du duel ! Préparez votre build.")
            
            # 1. Roulette des pouvoirs (9 fois)
            await player_data['member'].send("Vous allez recevoir 9 choix de pouvoirs.")
            for i in range(9):
                await self.run_power_roulette(player_data, game_mode='pvp') # game_mode='pvp' pour ne pas donner de durabilité
                await player_data['member'].send(f"Choix de pouvoir {i+1}/9 effectué.")
                await asyncio.sleep(1)
            
            # 2. Roulette des équipements (3 fois)
            await player_data['member'].send("Vous allez maintenant recevoir 3 choix d'équipements.")
            for i in range(3):
                await self.run_equipment_roulette(player_data, game_mode='pvp')
                await player_data['member'].send(f"Choix d'équipement {i+1}/3 effectué.")
                await asyncio.sleep(1)

            await player_data['member'].send("Phase de choix terminée ! Composez votre équipe et lancez le combat quand vous serez prêt.")

        else: # game_mode == 'pve'
            # --- LOGIQUE EXISTANTE POUR L'AVENTURE PVE ---
            num_roulettes = 5
            await player_data['member'].send(f"La roulette des pouvoirs commence ! Vous allez recevoir {num_roulettes} choix.")
            for i in range(num_roulettes):
                await self.run_power_roulette(player_data, game_mode='pve')
                await player_data['member'].send(f"Choix {i+1}/{num_roulettes} effectué.")
                await asyncio.sleep(1)
            await player_data['member'].send("Roulette des pouvoirs terminée ! Vous pouvez maintenant gérer votre inventaire.")

        # Dans les deux cas, on envoie les inventaires à la fin
        await self._send_reserve_view_dm(player_data)
        await self._send_inventories_dm(player_data)

    async def run_game_loop(self, game_state):
        """
        Boucle de jeu principale pour le mode PvP (Duel Unique).
        Gère la phase de setup, la préparation, le combat unique et l'annonce du vainqueur.
        """
        player_ids = list(game_state['players'].keys())
        p1_id, p2_id = player_ids[0], player_ids[1]
        p1_data = game_state['players'][p1_id]
        p2_data = game_state['players'][p2_id]
        
        channel = self.bot.get_channel(game_state['channel_id'])
        combat_cog = self.bot.get_cog('CombatCog')

        # --- PHASE 1: SETUP INITIAL (9 pouvoirs, 3 équipements) ---
        await channel.send("La phase de préparation commence ! Vérifiez vos messages privés pour choisir vos pouvoirs et équipements.")
        
        setup_tasks = []
        for p_id, p_data in game_state['players'].items():
            if not p_data['member'].bot:
                task = asyncio.create_task(self._player_setup_phase(p_data, game_state['game_mode']))
                setup_tasks.append(task)
        
        if setup_tasks:
            await asyncio.gather(*setup_tasks)
        
        # --- PHASE 2: PRÉPARATION FINALE ---
        game_state['combat_ready_event'] = asyncio.Event()
        for p_data in game_state['players'].values():
            if not p_data['member'].bot:
                p_data['is_ready'] = False

        await channel.send(
            embed=discord.Embed(
                title="Phase de Préparation du Duel",
                description="Composez votre équipe dans vos messages privés. Une fois que les deux joueurs sont prêts, le combat final commencera !",
                color=discord.Color.blue()
            ),
            view=PreparationView(self, game_state)
        )

        await game_state['combat_ready_event'].wait()

        # --- PHASE 3: LE COMBAT UNIQUE ---
        await channel.send("⚔️ **Le Duel commence !** ⚔️")
        
        log_message = await channel.send(embed=discord.Embed(title="⚔️ Combat en cours... ⚔️", color=discord.Color.red()))

        combat_result = await combat_cog.lancer_combat_engine(
            log_message=log_message,
            team_a=p1_data['reserve_combat'],
            team_b=p2_data['reserve_combat'],
            titre_combat=f"Duel entre {p1_data['member'].display_name} et {p2_data['member'].display_name}",
            nom_joueur=p1_data['member'].name,
            nom_adversaire=p2_data['member'].name
        )

        # --- PHASE 4: FIN DE PARTIE ---
        if not combat_result or not combat_result.get('winner_id'):
            await channel.send("❌ Erreur durant le combat. Fin de la partie.")
        else:
            winner_id = combat_result['winner_id']
            winner_data = game_state['players'][winner_id]
            await channel.send(f"🎉 **La partie est terminée ! Le grand vainqueur du duel est {winner_data['member'].mention} !** 🎉")

        del self.active_games[channel.id]

    

    async def run_power_roulette(self, player_data, rounds=1,game_mode='pve'):
        for _ in range(rounds):
            choices = random.sample(list(self.bot.catalogue_de_pouvoirs.values()), 3)
            
            view = discord.ui.View(timeout=180) # 3 minutes pour choisir
            
            # On a besoin d'une fonction qui sera appelée par les boutons
            async def button_callback(interaction: discord.Interaction):
                # On récupère le nom du pouvoir depuis l'ID custom du bouton
                chosen_power_name = interaction.data['custom_id']
                
                # On crée une copie pour s'assurer que c'est un objet unique
                chosen_power_data = copy.deepcopy(self.bot.catalogue_de_pouvoirs[chosen_power_name])
                if game_mode == 'pve':                    
                    chosen_power_data['durability'] = 5 # On ajoute la durabilité seulement en PvE
                
                player_data['inventory']['pouvoirs'].append(chosen_power_data)
                
                await interaction.response.send_message(f"Vous avez choisi **{chosen_power_name}**.", ephemeral=True)
                view.stop() # Arrête la vue pour empêcher un autre choix
                await self._send_inventories_dm(player_data)

            for power in choices:
                # L'ID custom est un moyen simple de passer une info (ici, le nom du pouvoir)
                button = discord.ui.Button(label=power['nom'], custom_id=power['nom'])
                button.callback = button_callback
                view.add_item(button)
                
            await player_data['member'].send("Choisissez un pouvoir :", view=view)
            await view.wait() # Le code attend ici que le joueur clique ou que le timeout soit atteint


    # Dans cogs/game_manager.py, dans la classe GameManagerCog

    async def run_equipment_roulette(self, player_data, rounds=1,game_mode='pve' ):
        """Lance la roulette d'équipement pour un joueur donné."""
        for _ in range(rounds):
            # Sélectionne aléatoirement 2 équipements du catalogue
            choices = random.sample(list(self.bot.catalogue_equipements.values()), 2)
            
            view = discord.ui.View(timeout=180) # 3 minutes pour choisir

            # Fonction de rappel pour gérer le choix de l'utilisateur
            async def button_callback(interaction: discord.Interaction):
                # Récupère le nom de l'équipement choisi depuis l'ID du bouton
                chosen_equip_name = interaction.data['custom_id']
                
                # Crée une copie pour s'assurer que c'est un objet unique
                chosen_equip_data = copy.deepcopy(self.bot.catalogue_equipements[chosen_equip_name])
                if game_mode == 'pve':                    
                    chosen_equip_data['durability'] = 2 # Définit la durabilité seulement en PvE
                
                # Ajoute l'équipement choisi à l'inventaire du joueur
                player_data['inventory']['equipements'].append(chosen_equip_data)
                
                await interaction.response.send_message(f"Vous avez choisi **{chosen_equip_name}**.", ephemeral=True)
                view.stop() # Arrête la vue pour empêcher un autre choix
                await self._send_inventories_dm(player_data)

            for equip in choices:
                # L'ID custom est utilisé pour passer le nom de l'équipement
                button = discord.ui.Button(label=equip['nom'], custom_id=equip['nom'])
                button.callback = button_callback
                view.add_item(button)
            
            # Envoie le message au joueur pour choisir un équipement
            await player_data['member'].send("Choisissez un équipement :", view=view)
            await view.wait() # Attend ici que le joueur clique ou que le délai d'attente soit atteint


    # Dans cogs/game_manager.py, à l'intérieur de la classe GameManagerCog

    # --- NOUVELLE FONCTION POUR ENVOYER LA RÉSERVE ---
    # Dans cogs/game_manager.py, dans la classe GameManagerCog

    async def _send_reserve_view_dm(self, player_state, interaction: discord.Interaction = None):
        """Génère, envoie et nettoie la vue de la réserve en MP."""
        
        # On prépare le contenu du message (embed + vue)
        embed = discord.Embed(title=f"Réserve de Partie de {player_state['member'].name}", color=discord.Color.orange())
        # ... (toute la logique pour remplir l'embed reste la même) ...
        for i, perso in enumerate(player_state['reserve_combat']):
            if perso:

                pv_base = perso['pv']                                
                # On prépare une variable temporaire pour l'affichage                
                pv_a_afficher = pv_base                                
                # On vérifie si l'équipement est le Grimoire interdit                
                if perso.get("equipement") and perso["equipement"].get("nom") == "Grimoire interdit":                    
                    # On calcule la nouvelle valeur, mais SANS modifier l'objet 'perso'                    
                    pv_a_afficher = math.ceil(pv_base * 0.25)
                attaque_base = perso['attaque']                
                attaque_a_afficher = attaque_base                
                if perso.get("equipement") and perso["equipement"].get("nom") == "Hachoir":                    
                    attaque_a_afficher = attaque_base + 3
                if perso.get("equipement") and perso["equipement"].get("nom") == "Lance-bouclier":                    
                    attaque_a_afficher += 5                    
                    # Pour les PV, on se base sur les PV du catalogue, pas les PV actuels potentiellement réduits                    
                    perso_catalogue = self.bot.catalogue_personnages.get(perso['nom'], {})                    
                    pv_catalogue = perso_catalogue.get('pv', pv_base)                    
                    pv_a_afficher = pv_catalogue + 5
                details = (f"**Attaque :** {attaque_a_afficher} | **PV :** {pv_a_afficher}\n"
                           f"**Niveau :** {perso.get('niveau', 1)} | **XP :** {perso.get('xp', 0)}")
                if perso.get("equipement"): details += f"\n**Équipement :** {perso['equipement']['nom']}(Dur: {perso['equipement'].get('durability', 'N/A')})\n" 
                else: details += f"\n**Équipement :** Vide"
                pouvoirs_str = ""
                for j, p in enumerate(perso.get("pouvoirs", [None, None, None])):
                    if p:
                        display_chance = ""
                        if p['nom'] == "Chaos": display_chance = "??%"
                        else:
                            activation_chance = p['activation']
                            if p['nom'] == "Pile ou Face" and perso['nom'] == "Le Parieur": activation_chance = 50
                            elif p['nom'] == "Armure" and perso['nom'] == "La Samourai": activation_chance = 50
                            elif p['nom'] == "Batteries d'urgences" and perso['nom'] == "Le Robot": activation_chance = 50
                            elif p['nom'] == "Nécromancie" and perso['nom'] == "La Nécromancienne": activation_chance = 50
                            elif p['nom'] == "Bénédiction" and perso['nom'] == "La Qilin": activation_chance = 50
                            display_chance = f"{activation_chance}%"
                        pouvoirs_str += f"\n> Slot {j+1}: {p['nom']} ({display_chance}) (Dur: {p.get('durability', 'N/A')})"
                    else: pouvoirs_str += f"\n> Slot {j+1}: Vide"
                details += pouvoirs_str
                embed.add_field(name=f"Slot {i + 1} : {perso['nom']}", value=details, inline=False)
            else:
                embed.add_field(name=f"Slot {i + 1} : Vide", value="Utilisez `/equiper personnage`", inline=False)
        
        view = ReserveView(self, player_state)

        # --- DÉBUT DE LA NOUVELLE LOGIQUE ---
        # Cas 1 : On peut éditer le message d'origine (le plus propre)
        if interaction and not interaction.is_expired() and interaction.message:
            await interaction.message.edit(embed=embed, view=view)
            player_state['last_reserve_message_id'] = interaction.message.id
        
        # Cas 2 : On doit envoyer un nouveau message
        else:
            # D'abord, on supprime l'ancien message s'il existe
            if player_state.get('last_reserve_message_id'):
                try:
                    dm_channel = player_state['member'].dm_channel or await player_state['member'].create_dm()
                    old_message = await dm_channel.fetch_message(player_state['last_reserve_message_id'])
                    await old_message.delete()
                except (discord.NotFound, discord.Forbidden):
                    # Pas de problème si le message a déjà été supprimé ou si on n'a pas les droits
                    pass
            
            # Ensuite, on envoie le nouveau message et on sauvegarde son ID
            new_message = await player_state['member'].send(embed=embed, view=view)
            player_state['last_reserve_message_id'] = new_message.id


    async def _send_inventories_dm(self, player_state, interaction: discord.Interaction = None):        
        """Génère, envoie et nettoie la vue de l'inventaire complet en MP."""        
        embed = discord.Embed(title=f"Inventaire de Partie de {player_state['member'].name}", color=discord.Color.dark_teal())                
        # Section Pouvoirs        
        if player_state['inventory']['pouvoirs']:            
            power_list_str = []            
            for p in player_state['inventory']['pouvoirs']:                
                # On vérifie si la durabilité existe avant de l'afficher                
                dura_text = f" (Dur: {p['durability']})" if 'durability' in p else ""                
                power_list_str.append(f"**{p['nom']}**{dura_text}")          
            embed.add_field(name="Pouvoirs", value="\n".join(power_list_str), inline=False)        
        else:            
            embed.add_field(name="Pouvoirs", value="Aucun pouvoir dans l'inventaire.", inline=False)        
        # Section Équipements        
        if player_state['inventory']['equipements']:            
            equip_list_str = []            
            for e in player_state['inventory']['equipements']:                
                # On fait la même vérification ici                
                dura_text = f" (Dur: {e['durability']})" if 'durability' in e else ""                
                equip_list_str.append(f"**{e['nom']}**{dura_text}")           
            embed.add_field(name="Équipements", value="\n".join(equip_list_str), inline=False)        
        else:            
            embed.add_field(name="Équipements", value="Aucun équipement dans l'inventaire.", inline=False)                
            # On crée la vue qui contiendra les boutons pour les deux types d'items        
        
        view = CombinedInventoryView(self, player_state)        
        # Logique de suppression/envoi        
        if player_state.get('last_inventory_message_id'):            
            try:                
                dm_channel = player_state['member'].dm_channel or await player_state['member'].create_dm()                
                old_message = await dm_channel.fetch_message(player_state['last_inventory_message_id'])                
                await old_message.delete()            
            except (discord.NotFound, discord.Forbidden):                
                pass                
            
        new_message = await player_state['member'].send(embed=embed, view=view)        
        player_state['last_inventory_message_id'] = new_message.id
        # --- FIN DE LA NOUVELLE LOGIQUE ---

# AJOUTEZ CETTE NOUVELLE CLASSE DANS cogs/game_manager.py

class InvitationView(discord.ui.View):
    def __init__(self, manager_cog, challenger: discord.Member, opponent: discord.Member):
        super().__init__(timeout=180) # L'invitation expire après 3 minutes
        self.manager_cog = manager_cog
        self.challenger = challenger
        self.opponent = opponent
        self.result = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # On s'assure que seule la personne défiée peut cliquer sur les boutons
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("Vous n'êtes pas la personne défiée.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = True
        self.stop() # Arrête la vue
        # On désactive les boutons pour montrer que le choix a été fait
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"✅ {self.opponent.mention} a accepté le défi de {self.challenger.mention} !", view=self)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = False
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"❌ {self.opponent.mention} a refusé le défi de {self.challenger.mention}.", view=self)

# --- VUE HELPER POUR SÉLECTIONNER UN PERSONNAGE À ÉQUIPER ---
class SelectCharacterView(discord.ui.View):
    def __init__(self, manager_cog, player_state, target_slot):
        super().__init__(timeout=180)
        self.manager_cog = manager_cog
        self.player_state = player_state
        self.target_slot = target_slot

        # On crée les options du menu déroulant à partir du catalogue global
        char_options = []
        # On récupère les noms des personnages déjà dans la réserve pour ne pas les proposer
        used_char_names = {p['nom'] for p in self.player_state['reserve_combat'] if p}
        
        for nom, perso_data in self.manager_cog.bot.catalogue_personnages.items():
            if nom not in used_char_names:
                char_options.append(discord.SelectOption(label=nom, value=nom))

        if not char_options:
            # Si aucune option n'est disponible, on ne peut rien faire
            self.add_item(discord.ui.Button(label="Aucun personnage disponible", disabled=True))
            return

        char_select = discord.ui.Select(placeholder="Choisir un personnage à équiper...", options=char_options)
        char_select.callback = self.select_callback
        self.add_item(char_select)

    async def select_callback(self, interaction: discord.Interaction):
        chosen_char_name = interaction.data['values'][0]
        perso_catalogue = self.manager_cog.bot.catalogue_personnages[chosen_char_name]

        perso_copy = copy.deepcopy(perso_catalogue)
        # Initialisation propre pour la partie
        perso_copy["pouvoirs"] = [None, None, None]
        perso_copy["equipement"] = None

        self.player_state["reserve_combat"][self.target_slot] = perso_copy

        await interaction.response.edit_message(content=f"**{chosen_char_name}** équipé dans le slot {self.target_slot + 1} !", view=None)
        
        # On rafraîchit TOUT
        await self.manager_cog._send_reserve_view_dm(self.player_state)
        await self.manager_cog._send_inventories_dm(self.player_state)


# --- LA NOUVELLE VUE DE RÉSERVE PRINCIPALE ---
class ReserveView(discord.ui.View):
    def __init__(self, manager_cog, player_state):
        super().__init__(timeout=None)
        self.manager_cog = manager_cog
        self.player_state = player_state

        # --- GESTION DES SLOTS DE PERSONNAGES (Lignes 0, 1, 2) ---
        for i in range(3):
            perso = self.player_state['reserve_combat'][i]
            if perso:
                # Slot plein : Boutons pour retirer le perso, les pouvoirs, l'équipement
                self.add_item(discord.ui.Button(label=f"Retirer {perso['nom']}", custom_id=f"remove_char_{i}", style=discord.ButtonStyle.danger, row=i))
                
                if perso.get("equipement"):
                    self.add_item(discord.ui.Button(label=f"Retirer {perso['equipement']['nom']}", custom_id=f"unequip_equip_{i}", style=discord.ButtonStyle.secondary, row=i))

                for p_idx, power in enumerate(perso.get("pouvoirs", [])):
                    if power:
                        self.add_item(discord.ui.Button(label=f"Retirer {power['nom']}", custom_id=f"unequip_power_{i}_{p_idx}", style=discord.ButtonStyle.secondary, row=i))
            else:
                # Slot vide : Bouton pour équiper un personnage
                self.add_item(discord.ui.Button(label=f"Équiper Personnage Slot {i+1}", custom_id=f"equip_char_{i}", style=discord.ButtonStyle.success, row=i))

        # --- GESTION DES DÉPLACEMENTS (Ligne 4) ---
        # On ajoute des boutons pour déplacer s'il y a au moins 2 personnages
        filled_slots = [i for i, p in enumerate(self.player_state['reserve_combat']) if p]
        if len(filled_slots) >= 2:
            # On crée toutes les paires possibles pour le déplacement
            if 0 in filled_slots and 1 in filled_slots:
                self.add_item(discord.ui.Button(label="Slot 1 ↔ 2", custom_id="move_0_1", style=discord.ButtonStyle.blurple, row=4))
            if 0 in filled_slots and 2 in filled_slots:
                self.add_item(discord.ui.Button(label="Slot 1 ↔ 3", custom_id="move_0_2", style=discord.ButtonStyle.blurple, row=4))
            if 1 in filled_slots and 2 in filled_slots:
                self.add_item(discord.ui.Button(label="Slot 2 ↔ 3", custom_id="move_1_2", style=discord.ButtonStyle.blurple, row=4))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # On attache tous les callbacks à une seule méthode pour la gestion
        # On utilise startswith pour gérer les ID dynamiques
        custom_id = interaction.data['custom_id']
        
        if custom_id.startswith("equip_char_"):
            await self.equip_char_callback(interaction)
        elif custom_id.startswith("remove_char_"):
            await self.remove_char_callback(interaction)
        elif custom_id.startswith("unequip_equip_"):
            await self.unequip_equip_callback(interaction)
        elif custom_id.startswith("unequip_power_"):
            await self.unequip_power_callback(interaction)
        elif custom_id.startswith("move_"):
            await self.move_char_callback(interaction)
            
        return False # On empêche l'interaction de continuer plus loin

    async def equip_char_callback(self, interaction: discord.Interaction):
        slot_index = int(interaction.data['custom_id'].split('_')[-1])
        await interaction.response.send_message("Choisissez un personnage du catalogue :", view=SelectCharacterView(self.manager_cog, self.player_state, slot_index), ephemeral=True)

    async def remove_char_callback(self, interaction: discord.Interaction):
        slot_index = int(interaction.data['custom_id'].split('_')[-1])
        perso_a_retirer = self.player_state["reserve_combat"][slot_index]
        
        # Remettre les pouvoirs et équipements dans l'inventaire de partie
        for p in perso_a_retirer.get("pouvoirs", []):
            if p: self.player_state['inventory']['pouvoirs'].append(p)
        if perso_a_retirer.get("equipement"):
            self.player_state['inventory']['equipements'].append(perso_a_retirer["equipement"])
            
        self.player_state["reserve_combat"][slot_index] = None
        
        await interaction.response.defer()
        await self.manager_cog._send_reserve_view_dm(self.player_state)
        await self.manager_cog._send_inventories_dm(self.player_state)

    async def move_char_callback(self, interaction: discord.Interaction):
        _, slot1_str, slot2_str = interaction.data['custom_id'].split('_')
        slot1, slot2 = int(slot1_str), int(slot2_str)
        
        reserve = self.player_state["reserve_combat"]
        reserve[slot1], reserve[slot2] = reserve[slot2], reserve[slot1]
        
        await interaction.response.defer()
        await self.manager_cog._send_reserve_view_dm(self.player_state)

    async def unequip_power_callback(self, interaction: discord.Interaction):
        _, _, char_index_str, power_index_str = interaction.data['custom_id'].split('_')
        char_index, power_index = int(char_index_str), int(power_index_str)
        
        personnage = self.player_state['reserve_combat'][char_index]
        pouvoir_a_retirer = personnage['pouvoirs'][power_index]
        
        personnage['pouvoirs'][power_index] = None
        self.player_state['inventory']['pouvoirs'].append(pouvoir_a_retirer)

        await interaction.response.defer()
        await self.manager_cog._send_reserve_view_dm(self.player_state)
        await self.manager_cog._send_inventories_dm(self.player_state)

    async def unequip_equip_callback(self, interaction: discord.Interaction):
        _, _, char_index_str = interaction.data['custom_id'].split('_')
        char_index = int(char_index_str)

        personnage = self.player_state['reserve_combat'][char_index]
        equipement_a_retirer = personnage['equipement']
        
        personnage['equipement'] = None
        self.player_state['inventory']['equipements'].append(equipement_a_retirer)

        await interaction.response.defer()
        await self.manager_cog._send_reserve_view_dm(self.player_state)
        await self.manager_cog._send_inventories_dm(self.player_state)


# --- VUE POUR CHOISIR OÙ ÉQUIPER UN POUVOIR ---
class EquipTargetView(discord.ui.View):
    def __init__(self, manager_cog, player_state, power_to_equip):
        super().__init__(timeout=180)
        self.manager_cog = manager_cog
        self.player_state = player_state
        self.power_to_equip = power_to_equip
        self.char_slot = None
        self.power_slot = None

        # Menu déroulant pour choisir le personnage
        char_options = []
        for i, perso in enumerate(self.player_state['reserve_combat']):
            if perso:
                char_options.append(discord.SelectOption(label=f"Slot {i+1}: {perso['nom']}", value=str(i)))
        
        char_select = discord.ui.Select(placeholder="Choisir un personnage...", options=char_options)
        char_select.callback = self.char_select_callback
        self.add_item(char_select)

        # Menu déroulant pour choisir le slot de pouvoir
        power_options = [discord.SelectOption(label=f"Slot de pouvoir {i+1}", value=str(i)) for i in range(3)]
        power_select = discord.ui.Select(placeholder="Choisir un slot de pouvoir...", options=power_options)
        power_select.callback = self.power_select_callback
        self.add_item(power_select)

        # Bouton pour confirmer
        confirm_button = discord.ui.Button(label="Confirmer", style=discord.ButtonStyle.success, disabled=True)
        confirm_button.callback = self.confirm_callback
        self.add_item(confirm_button)

    async def char_select_callback(self, interaction: discord.Interaction):
        self.char_slot = int(interaction.data['values'][0])
        self.children[2].disabled = self.power_slot is None # Active le bouton si l'autre choix est fait
        await interaction.response.edit_message(view=self)

    async def power_select_callback(self, interaction: discord.Interaction):
        self.power_slot = int(interaction.data['values'][0])
        self.children[2].disabled = self.char_slot is None # Active le bouton si l'autre choix est fait
        await interaction.response.edit_message(view=self)

    async def confirm_callback(self, interaction: discord.Interaction):
        # On effectue l'équipement
        target_char = self.player_state['reserve_combat'][self.char_slot]
        
        # S'il y a déjà un pouvoir, on le remet dans l'inventaire
        if target_char['pouvoirs'][self.power_slot]:
            old_power = target_char['pouvoirs'][self.power_slot]
            self.player_state['inventory']['pouvoirs'].append(old_power)

        target_char['pouvoirs'][self.power_slot] = copy.deepcopy(self.power_to_equip)
        self.player_state['inventory']['pouvoirs'].remove(self.power_to_equip)

        await interaction.response.edit_message(content=f"**{self.power_to_equip['nom']}** équipé sur **{target_char['nom']}** !", view=None)
        # On envoie la nouvelle vue de la réserve mise à jour
        await self.manager_cog._send_reserve_view_dm(self.player_state)
        await self.manager_cog._send_inventories_dm(self.player_state)
# ...

# --- AJOUTER CES 3 NOUVELLES CLASSES DE VUES DANS game_manager.py ---

# VUE POUR CHOISIR SUR QUI ÉQUIPER UN ÉQUIPEMENT
class EquipEquipmentTargetView(discord.ui.View):
    def __init__(self, manager_cog, player_state, equipment_to_equip):
        super().__init__(timeout=180)
        self.manager_cog = manager_cog
        self.player_state = player_state
        self.equipment_to_equip = equipment_to_equip

        char_options = []
        for i, perso in enumerate(self.player_state['reserve_combat']):
            if perso:
                char_options.append(discord.SelectOption(label=f"Slot {i+1}: {perso['nom']}", value=str(i)))
        
        char_select = discord.ui.Select(placeholder="Choisir un personnage...", options=char_options)
        char_select.callback = self.confirm_callback
        self.add_item(char_select)

    async def confirm_callback(self, interaction: discord.Interaction):
        char_slot = int(interaction.data['values'][0])
        target_char = self.player_state['reserve_combat'][char_slot]

        if target_char.get('equipement'):
            old_equip = target_char['equipement']
            self.player_state['inventory']['equipements'].append(old_equip)

        target_char['equipement'] = copy.deepcopy(self.equipment_to_equip)
        self.player_state['inventory']['equipements'].remove(self.equipment_to_equip)

        await interaction.response.edit_message(content=f"**{self.equipment_to_equip['nom']}** équipé sur **{target_char['nom']}** !", view=None)
        
        # On met à jour les deux vues
        await self.manager_cog._send_reserve_view_dm(self.player_state)
        await self.manager_cog._send_inventories_dm(self.player_state)

# VUE QUI COMBINE LES BOUTONS POUVOIRS ET ÉQUIPEMENTS
# REMPLACEZ VOTRE ANCIENNE CLASSE "CombinedInventoryView" PAR CELLE-CI

class CombinedInventoryView(discord.ui.View):
    def __init__(self, manager_cog, player_state):
        super().__init__(timeout=None)
        self.manager_cog = manager_cog
        self.player_state = player_state

        # --- MENU DÉROULANT POUR LES POUVOIRS ---
        if self.player_state['inventory']['pouvoirs']:
            # On crée les options pour le menu déroulant
            power_options = []
            # On utilise enumerate pour avoir un identifiant unique (l'index) pour chaque pouvoir
            for index, power in enumerate(self.player_state['inventory']['pouvoirs']):
                # On ne prend que les 25 premiers pour respecter la limite de Discord
                if len(power_options) < 25:
                    dura_text = f" (Dur: {power['durability']})" if 'durability' in power else ""                    
                    power_options.append(                        
                                         discord.SelectOption(                            
                                                              label=f"{power['nom']}{dura_text}", # On utilise le texte conditionnel                            
                                                              value=f"power_{index}"                        
                                                              )                    
                                         )
            
            power_select = discord.ui.Select(
                placeholder="Équiper un pouvoir...",
                options=power_options,
                custom_id="equip_power_select"
            )
            power_select.callback = self.select_callback # On lie le menu à une fonction
            self.add_item(power_select)

        # --- MENU DÉROULANT POUR LES ÉQUIPEMENTS ---
        if self.player_state['inventory']['equipements']:
            equip_options = []
            for index, equip in enumerate(self.player_state['inventory']['equipements']):
                if len(equip_options) < 25:
                    dura_text = f" (Dur: {equip['durability']})" if 'durability' in equip else ""                    
                    equip_options.append(                        
                                         discord.SelectOption(                            
                                                              label=f"{equip['nom']}{dura_text}", # On utilise le texte conditionnel                            
                                                              value=f"equip_{index}"                        
                                                              )                   
                                         )

            equip_select = discord.ui.Select(
                placeholder="Équiper un équipement...",
                options=equip_options,
                custom_id="equip_equip_select"
            )
            equip_select.callback = self.select_callback # La même fonction gère les deux menus
            self.add_item(equip_select)

    async def select_callback(self, interaction: discord.Interaction):
        # On vérifie qu'il y a au moins un personnage dans la réserve
        if not any(p for p in self.player_state['reserve_combat']):
            return await interaction.response.send_message("Vous devez avoir un personnage dans la réserve.", ephemeral=True)
            
        # On récupère la valeur choisie, ex: "power_5" ou "equip_2"
        chosen_value = interaction.data['values'][0]
        item_type, item_index_str = chosen_value.split('_')
        item_index = int(item_index_str)

        if item_type == "power":
            power_to_equip = self.player_state['inventory']['pouvoirs'][item_index]
            target_view = EquipTargetView(self.manager_cog, self.player_state, power_to_equip)
            await interaction.response.send_message(f"Où équiper **{power_to_equip['nom']}** ?", view=target_view, ephemeral=True)
        
        elif item_type == "equip":
            equip_to_equip = self.player_state['inventory']['equipements'][item_index]
            target_view = EquipEquipmentTargetView(self.manager_cog, self.player_state, equip_to_equip)
            await interaction.response.send_message(f"Sur qui équiper **{equip_to_equip['nom']}** ?", view=target_view, ephemeral=True)



# --- VUE PRINCIPALE DE L'INVENTAIRE ---
class InventoryView(discord.ui.View):
    def __init__(self, manager_cog, player_state):
        super().__init__(timeout=None)
        self.manager_cog = manager_cog
        self.player_state = player_state

        # On crée un bouton pour chaque pouvoir dans l'inventaire
        for index, power in enumerate(self.player_state['inventory']['pouvoirs']):
            button = discord.ui.Button(
                label=f"Équiper {power['nom']} (Dur: {power['durability']})",
                custom_id=f"equip_{index}",
                style=discord.ButtonStyle.primary
            )
            button.callback = self.equip_callback
            self.add_item(button)

    async def equip_callback(self, interaction: discord.Interaction):

        if not any(p for p in self.player_state['reserve_combat']):            
            await interaction.response.send_message(                
                "Vous devez d'abord placer un personnage dans votre réserve avant de pouvoir équiper un pouvoir.",                
                ephemeral=True            )            
            return # On arrête la fonction ici
        power_index = int(interaction.data['custom_id'].split('_')[1])
        if power_index >= len(self.player_state['inventory']['pouvoirs']):            
            return await interaction.response.send_message("L'inventaire a changé, veuillez relancer la commande.", ephemeral=True)
        power_to_equip = self.player_state['inventory']['pouvoirs'][power_index]
        
        # On envoie la vue pour choisir la cible
        target_view = EquipTargetView(self.manager_cog, self.player_state, power_to_equip)
        await interaction.response.send_message(
            f"Où équiper **{power_to_equip['nom']}** ?",
            view=target_view,
            ephemeral=True
        )


# Dans cogs/game_manager.py

# DANS cogs/game_manager.py

class PreparationView(discord.ui.View):
    
    def __init__(self, manager_cog, game_state):
        super().__init__(timeout=None)
        self.manager_cog = manager_cog
        self.game_state = game_state

        game_mode = self.game_state.get('game_mode', 'pve')

        # --- NOUVELLE LOGIQUE D'AFFICHAGE CONDITIONNEL ---

        if game_mode == 'pvp':
            # En PvP, on ne met que le bouton "Prêt"
            ready_button = discord.ui.Button(label="Prêt pour le Duel", style=discord.ButtonStyle.success)
            ready_button.callback = self.ready_callback
            self.add_item(ready_button)
        else: # En PvE, on garde l'ancienne logique
            power_button = discord.ui.Button(label="Roulette des Pouvoirs (300 Gold)", style=discord.ButtonStyle.primary)
            power_button.callback = self.power_roulette_callback
            self.add_item(power_button)

            equipment_button = discord.ui.Button(label="Roulette des Équipements (200 Gold)", style=discord.ButtonStyle.primary)
            equipment_button.callback = self.equipment_roulette_callback
            self.add_item(equipment_button)

            ready_button = discord.ui.Button(label="Prêt", style=discord.ButtonStyle.success)
            ready_button.callback = self.ready_callback
            self.add_item(ready_button)
    # --- DÉBUT DE LA STRUCTURE CORRECTE ---

    async def _execute_roulette_task(self, interaction: discord.Interaction, roulette_type: str):        
        """Fonction interne qui contient la logique LENTE, exécutée en arrière-plan."""        
        player_data = self.game_state.get('players', {}).get(interaction.user.id) or self.game_state.get('player')                
        # On récupère le mode de jeu depuis le game_state        
        game_mode = self.game_state.get('game_mode', 'pve') # 'pve' par défaut pour la sécurité        
        if roulette_type == "power":            
            player_data['gold'] -= 300                        
            # On détermine le nombre de tours de roulette            
            power_rounds = 2 if game_mode == 'pvp' else 5                        
            # On passe les bons arguments à la fonction            
            await self.manager_cog.run_power_roulette(player_data, rounds=power_rounds, game_mode=game_mode)                
        elif roulette_type == "equipment":            
            player_data['gold'] -= 200            
            # On détermine le nombre de tours de roulette            
            equip_rounds = 1 if game_mode == 'pvp' else 3                        
            # On passe les bons arguments à la fonction            
            await self.manager_cog.run_equipment_roulette(player_data, rounds=equip_rounds, game_mode=game_mode)

    async def power_roulette_callback(self, interaction: discord.Interaction):
        player_data = self.game_state.get('players', {}).get(interaction.user.id) or self.game_state.get('player')
        
        if not player_data or player_data['gold'] < 300:
            return await interaction.response.send_message("Vous n'avez pas assez de gold.", ephemeral=True)

        # 1. Répondre immédiatement
        await interaction.response.send_message("Roulette des pouvoirs lancée ! Vérifiez vos messages privés.", ephemeral=True)
        
        # 2. Lancer la longue tâche en arrière-plan et ne PAS attendre qu'elle finisse
        asyncio.create_task(self._execute_roulette_task(interaction, "power"))

    async def equipment_roulette_callback(self, interaction: discord.Interaction):
        player_data = self.game_state.get('players', {}).get(interaction.user.id) or self.game_state.get('player')

        if not player_data or player_data['gold'] < 200:
            return await interaction.response.send_message("Vous n'avez pas assez de gold.", ephemeral=True)

        # 1. Répondre immédiatement
        await interaction.response.send_message("Roulette des équipements lancée ! Vérifiez vos messages privés.", ephemeral=True)

        # 2. Lancer la longue tâche en arrière-plan et ne PAS attendre qu'elle finisse
        asyncio.create_task(self._execute_roulette_task(interaction, "equipment"))

    # --- FIN DE LA STRUCTURE CORRECTE ---

        # REMPLACE CETTE FONCTION DANS TON CODE
    
    async def ready_callback(self, interaction: discord.Interaction):
        # On récupère les données du joueur qui a cliqué
        player_data = self.game_state.get('players', {}).get(interaction.user.id) or self.game_state.get('player')
        
        if not player_data:
            # Sécurité au cas où le joueur ne serait pas trouvé
            return await interaction.response.send_message("Erreur : Impossible de vous identifier dans cette partie.", ephemeral=True)

        # On vérifie que sa réserve est bien complète (3 personnages)
        if any(p is None for p in player_data['reserve_combat']):
            return await interaction.response.send_message("⚠️ Votre réserve de combat doit être complète (3 personnages) avant de pouvoir lancer le combat.", ephemeral=True)
        
        # On le marque comme prêt et on l'annonce
        player_data['is_ready'] = True
        await interaction.response.send_message(f"{interaction.user.mention} est prêt !", ephemeral=False)
        
        # --- NOUVELLE LOGIQUE CORRIGÉE ---
        
        # Cas 1 : C'est une partie PvP (elle a un dictionnaire 'players')
        if 'players' in self.game_state:
            # On appelle la fonction qui va vérifier si TOUS les joueurs sont prêts
            await self.manager_cog.start_combat(self.game_state)
            
        # Cas 2 : C'est une partie PvE (elle a un seul 'player')
        else:
            # En PvE, un seul joueur suffit pour lancer le combat
            self.game_state['combat_ready_event'].set()



async def setup(bot: commands.Bot):
    await bot.add_cog(GameManagerCog(bot))



     
