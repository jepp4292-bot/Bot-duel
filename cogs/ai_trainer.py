# cogs/ai_trainer.py
import discord
import random
import copy
import asyncio

class AITrainer:
    """IA stratégique et adaptative pour les duels 1v1."""
    
    def __init__(self, bot):
        self.bot = bot
        
    # =====================================================================================
    # SECTION 1 : ANALYSE ET ÉVALUATION
    # =====================================================================================

    def analyser_situation(self, player_state, opponent_state):
        """
        Analyse la situation du jeu et retourne un score de danger pour l'IA.
        Le score va de 0 (sûr) à 100 (très dangereux).
        """
        player_hp = player_state['hp']
        opponent_hp = opponent_state['hp']
        player_pr = player_state['pr']
        opponent_pr = opponent_state['pr']
        
        danger_score = 0
        
        # Danger si les HP de l'IA sont bas
        if player_hp < 15:
            danger_score += 40
        elif player_hp < 25:
            danger_score += 20
        
        # Danger si l'adversaire a une grosse avance en PR
        if opponent_pr > player_pr + 5:
            danger_score += 15
        
        # Danger si l'adversaire a un personnage puissant sur le terrain
        if opponent_state.get('terrain'):
            opponent_char = opponent_state['terrain']
            # Un personnage avec plus de 6 d'attaque est une menace immédiate
            if opponent_char['attaque'] > 6:
                danger_score += 20
            # Un personnage avec beaucoup de PV est difficile à tuer
            if opponent_char.get('pv_max', opponent_char['pv']) > 10:
                danger_score += 10
        
        # Danger si l'adversaire a plus de personnages prêts au combat
        player_chars_count = sum(1 for c in player_state['inventaire'] if c) + (1 if player_state['terrain'] else 0)
        opponent_chars_count = sum(1 for c in opponent_state['inventaire'] if c) + (1 if opponent_state['terrain'] else 0)
        if opponent_chars_count > player_chars_count:
            danger_score += 10
            
        return min(danger_score, 100)

    def scorer_personnage(self, char, player_state, opponent_state, situation_danger):
        """
        Donne un score de pertinence à un personnage en fonction du contexte du jeu.
        Un score plus élevé signifie que le personnage est un meilleur choix à ce moment précis.
        """
        score = 0
        
        # Score de base basé sur les stats brutes
        score += char.get('pv_max', char['pv']) * 2.5  # La survie est importante
        score += char['attaque'] * 3.0  # Les dégâts sont la clé de la victoire
        
        # Bonus/Malus en fonction de la situation de danger
        if situation_danger > 60:  # Situation critique, besoin de défense
            score += char.get('pv_max', char['pv']) * 2  # Priorité aux tanks
        elif situation_danger < 30:  # Situation favorable, on pousse l'avantage
            score += char['attaque'] * 4  # Priorité aux attaquants
        
        # Bonus spécifiques pour certains rôles clés
        nom = char['nom']
        
        if nom in ["Monstre foyer", "Autel vivant", "Chevalier coton", "Paresseuse"]:  # Rôle de tank
            if situation_danger > 50: score += 30
        
        if nom in ["Oncle ben", "Pyromane", "Mini Hercule", "Renarde", "Artiste"]:  # Rôle de DPS
            if situation_danger < 40: score += 35
        
        if nom in ["Robot radio", "Mage des nuages", "Cape guerrière", "Garçon parapluie"]:  # Rôle de support/utilitaire
            if len([c for c in player_state['inventaire'] if c]) > 1: # Plus utile si on a des alliés
                score += 20

        # Malus si le personnage est fatigué et ne peut pas être placé
        if "Fatigue d'invocation" in char.get("statuts", []):
            score -= 100 # Très gros malus, on ne veut pas l'invoquer si on a besoin de le jouer tout de suite

        return score
    
    def evaluer_etat_adversaire(self, opponent_state):
        """Retourne une évaluation simple de l'état de l'adversaire."""
        if opponent_state['hp'] <= 15:
            return "FAIBLE"
        if opponent_state['hp'] >= 40 and opponent_state['pr'] >= 8:
            return "FORT"
        return "NORMAL"

    # =====================================================================================
    # SECTION 2 : LOGIQUE DE DÉCISION
    # =====================================================================================

    def choisir_passif(self, player_state, available_passives, game_state):
        """Choisit un passif de manière stratégique en fonction du tour de jeu."""
        tour = game_state['tour']
        
        # Au tour 5, on se prépare pour la fin de partie : la survie est clé.
        if tour == 5:
            priority = [
                "second_chance", "volonte", "human_tide", "mode_facile", 
                "vif", "promotion", "a_main_nue", "absenteism", "maitre_capacites", "pret"
            ]
        # Au début (tour 2), on veut construire un avantage.
        else:
            priority = [
                "a_main_nue", "human_tide", "vif", "mode_facile",
                "promotion", "maitre_capacites", "second_chance", "volonte",
                "absenteism", "pret"
            ]
        
        for passive_id in priority:
            if passive_id in available_passives:
                player_state['passives'][passive_id] = True
                print(f"[IA LOG - Passif] L'IA a choisi : {passive_id} (Tour {tour})")
                return

    def generer_choix_invocation(self, player_state):
        """Génère 3 choix de personnages que l'IA peut s'offrir."""
        available_chars = [
            char for char in self.bot.catalogue_personnages_1v1.values()
            if char['cout'] <= player_state['pr']
        ]
        
        if not available_chars:
            return []
        
        chars_by_cost = {}
        for char in available_chars:
            cost = char['cout']
            if cost not in chars_by_cost:
                chars_by_cost[cost] = []
            chars_by_cost[cost].append(char)
        
        possible_costs = list(chars_by_cost.keys())
        num_choices = min(3, len(possible_costs))
        chosen_costs = random.sample(possible_costs, num_choices)
        
        choices = [random.choice(chars_by_cost[cost]) for cost in chosen_costs]
        return choices

    def choisir_personnage_invocation(self, choices, player_state, opponent_state, game_state):
        """L'IA choisit le personnage le plus pertinent parmi les 3 options en utilisant le scoring."""
        if not choices:
            return None
        
        danger = self.analyser_situation(player_state, opponent_state)
        
        best_char = None
        best_score = -1
        
        for char in choices:
            score = self.scorer_personnage(char, player_state, opponent_state, danger)
            print(f"[IA DEBUG - Invocation] Évaluation de {char['nom']}: score {score:.2f} (Danger: {danger})")
            
            if score > best_score:
                best_score = score
                best_char = char
        
        print(f"[IA LOG - Invocation] L'IA a choisi d'invoquer {best_char['nom']} (Score: {best_score:.2f})")
        return best_char

    def placer_strategiquement(self, player_state, opponent_state, game_state):
        """
        Décide quel personnage placer sur le terrain.
        Privilégie la défense en début de partie ou en cas de danger, sinon l'attaque.
        """
        placeable = [
            char for char in player_state['inventaire']
            if char and "Fatigue d'invocation" not in char.get("statuts", [])
        ]
        
        if not placeable:
            return False
        
        danger = self.analyser_situation(player_state, opponent_state)
        tour = game_state['tour']
        
        # Stratégie de sélection
        if tour <= 2: # Début de partie, on veut un terrain solide
            best_char_to_place = max(placeable, key=lambda c: c.get('pv_max', c['pv']))
        elif danger > 50: # Si l'IA est en danger, elle place son meilleur tank
            best_char_to_place = max(placeable, key=lambda c: c.get('pv_max', c['pv']))
        else: # Sinon, elle place son meilleur attaquant
            best_char_to_place = max(placeable, key=lambda c: c['attaque'])
        
        # Logique de placement/remplacement
        if player_state['terrain']:
            current_char = player_state['terrain']
            # On ne remplace que si le nouveau personnage est significativement meilleur
            current_score = self.scorer_personnage(current_char, player_state, opponent_state, danger)
            new_score = self.scorer_personnage(best_char_to_place, player_state, opponent_state, danger)
            
            if new_score > current_score + 20: # Le seuil de +20 évite les changements inutiles
                idx = player_state['inventaire'].index(best_char_to_place)
                player_state['inventaire'][idx] = current_char
                player_state['terrain'] = best_char_to_place
                print(f"[IA LOG - Placement] Remplacement stratégique : {best_char_to_place['nom']} remplace {current_char['nom']}")
                return True
            return False # Pas de remplacement nécessaire
        else:
            player_state['inventaire'].remove(best_char_to_place)
            player_state['terrain'] = best_char_to_place
            print(f"[IA LOG - Placement] Placement initial : {best_char_to_place['nom']}")
            return True
            player_state['has_placed_character'] = True

    def utiliser_capacite_smart(self, player_state, opponent_state, game_state):
        """Utilise une capacité de manière intelligente en évaluant la meilleure option."""
        usable = []
        for i, char in enumerate(player_state['inventaire']):
            if char and "capacite" in char:
                capacite = char['capacite']
                complex_abilities = ["Dans les nuages", "Revêtement", "Oeuvre d'art", "Prière", "Esprit robuste"]
                if capacite['nom'] not in complex_abilities and player_state['pr'] >= capacite['cout']:
                    usable.append((i, char, capacite))
        
        if not usable:
            return False
        
        danger = self.analyser_situation(player_state, opponent_state)
        opponent_status = self.evaluer_etat_adversaire(opponent_state)
        
        best_choice = None
        best_priority = 0 # On n'active que si une capacité a une priorité > 0
        
        for i, char, capacite in usable:
            priority = 0
            nom = capacite['nom']
            
            # Priorité 1: Actions défensives si en danger
            if danger > 50:
                if nom in ["Repos du héros", "Bouclier coton"]: priority = 70
                elif nom == "Contre-attaque": priority = 65
            
            # Priorité 2: Actions offensives si l'adversaire est faible
            if opponent_status == "FAIBLE" or opponent_state['hp'] < 20:
                if nom in ["Attaque surprise", "Entrainement", "Bipolaire"]: priority = 80
                elif nom == "Boule de feu": priority = 90 # Très haute priorité pour finir le jeu
            
            # Priorité 3: Actions de contrôle et de préparation
            if nom in ["Cible", "Piratage", "Spores", "Bourrasque"]: priority = 40
            
            # Priorité de base pour les buffs simples
            if nom in ["Entrainement", "Musique de combat"]: priority = max(priority, 30)

            # Ajustement : Ne pas utiliser une capacité chère si on est bas en PR
            if capacite['cout'] > 3 and player_state['pr'] < 6:
                priority -= 20

            print(f"[IA DEBUG - Capacité] Évaluation de {nom}: Priorité {priority}")

            if priority > best_priority:
                best_priority = priority
                best_choice = (i, char, capacite)
        
        if not best_choice:
            return False
            
        i, char, capacite = best_choice
        player_state['pr'] -= capacite['cout']
        self.executer_effet_capacite(player_state, char, capacite)
        print(f"[IA LOG - Capacité] Utilisation intelligente de {capacite['nom']} (Priorité: {best_priority})")
        return True

    # =====================================================================================
    # SECTION 3 : EXÉCUTION (MÉTHODES UTILITAIRES)
    # =====================================================================================
    
    def executer_effet_capacite(self, player_state, char, capacite):
        """Exécute l'effet d'une capacité. Cette méthode reste la même."""
        nom_capacite = capacite['nom']
        
        if nom_capacite == "Repos du héros":
            char['pv'] = min(char['pv'] + 3, char['pv_max'])
        elif nom_capacite == "Entrainement":
            char['attaque'] += 3
        elif nom_capacite == "Bipolaire":
            char['pv'], char['attaque'] = char['attaque'], char['pv']
            if char['pv_max'] < char['pv']:
                char['pv_max'] = char['pv']
        elif nom_capacite in ["Attaque surprise", "Cible", "Bouclier coton", "Pluie battante", "Contre-attaque", "Souvenir inoubliable", "Boule de feu", "Petit effort", "Bourrasque", "Monologue ennuyeux", "Spores", "Gros câlin", "Vol", "Nuisible"]:
            status_map = {
                "Attaque surprise": "À l'affût", "Cible": "En chasse", "Bouclier coton": "Coton",
                "Pluie battante": "Parapluie", "Contre-attaque": "Contre", "Souvenir inoubliable": "Cadeau de Noël",
                "Boule de feu": "Incantation", "Petit effort": "Sommeil", "Bourrasque": "Typhon",
                "Monologue ennuyeux": "blablabla", "Spores": "Champignon", "Gros câlin": "Calin",
                "Vol": "Vol", "Nuisible": "Malicieux"
            }
            status = status_map[nom_capacite]
            if "statuts" not in char:
                char["statuts"] = []
            if status not in char["statuts"]:
                char["statuts"].append(status)
        elif nom_capacite == "Piratage":
            player_state['piratage_actif'] = True
            if "statuts" not in char:
                char["statuts"] = []
            if "Piratage" not in char["statuts"]:
                char["statuts"].append("Piratage")

async def setup(bot):
    """Fonction requise par Discord.py pour charger le cog."""
    pass