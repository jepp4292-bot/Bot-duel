# cogs/ai_trainer.py
# cogs/ia_trainer.py

import random
import copy
import logging
class AITrainer:
    """IA stratégique et adaptative pour les duels 1v1, basée sur des métadonnées (tags)."""
    
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
        danger_score = 0
        
        # Danger si les HP de l'IA sont bas
        if player_hp < 15: danger_score += 40
        elif player_hp < 25: danger_score += 20
        
        # Danger si l'adversaire a une grosse avance en PR
        if opponent_state['pr'] > player_state['pr'] + 5: danger_score += 15
        
        # Danger si l'adversaire a un personnage puissant sur le terrain
        if opponent_state.get('terrain'):
            opponent_char = opponent_state['terrain']
            if opponent_char['attaque'] > 6: danger_score += 20
            if opponent_char.get('pv_max', opponent_char['pv']) > 10: danger_score += 10
        
        # Danger si l'adversaire a plus de personnages
        player_chars_count = sum(1 for c in player_state['inventaire'] if c) + (1 if player_state['terrain'] else 0)
        opponent_chars_count = sum(1 for c in opponent_state['inventaire'] if c) + (1 if opponent_state['terrain'] else 0)
        if opponent_chars_count > player_chars_count: danger_score += 10
            
        return min(danger_score, 100)

    # === AMÉLIORATION MAJEURE : SCORING BASÉ SUR LES RÔLES ===
    def scorer_personnage(self, char, player_state, opponent_state, situation_danger):
        """
        Donne un score de pertinence à un personnage en fonction de ses rôles et du contexte.
        Cette méthode ne dépend plus des noms, mais des tags 'roles' que tu dois ajouter à tes personnages.
        """
        score = 0
        roles = char.get('roles', []) # On récupère les rôles du personnage (ex: ["tank", "support"])

        # Score de base basé sur les stats brutes
        score += char.get('pv_max', char['pv']) * 2.5
        score += char['attaque'] * 3.0
        
        # Bonus/Malus en fonction de la situation de danger
        if situation_danger > 60:  # Situation critique, besoin de défense
            score += char.get('pv_max', char['pv']) * 2
        elif situation_danger < 30:  # Situation favorable, on pousse l'avantage
            score += char['attaque'] * 4
        
        # Bonus spécifiques basés sur les RÔLES (beaucoup plus flexible !)
        if 'tank' in roles:
            if situation_danger > 50: score += 30
            else: score += 10 # Un tank est toujours utile
        
        if 'dps' in roles:
            if situation_danger < 40: score += 35
            else: score += 15 # Les dégâts sont toujours bons à prendre

        if 'support' in roles:
            # Un support est plus utile si on a déjà des alliés à buffer
            if len([c for c in player_state['inventaire'] if c]) > 1:
                score += 25
        
        if 'nuker' in roles: # Pour les personnages qui peuvent finir la partie
            if opponent_state['hp'] < 20: score += 50 # Très haute priorité si l'ennemi est faible

        # Malus si le personnage est fatigué et ne peut pas être placé ce tour-ci
        if "Fatigue d'invocation" in char.get("statuts", []):
            score -= 100

        return score
    
    def evaluer_etat_adversaire(self, opponent_state):
        """Retourne une évaluation simple de l'état de l'adversaire."""
        if opponent_state['hp'] <= 15: return "FAIBLE"
        if opponent_state['hp'] >= 40 and opponent_state['pr'] >= 8: return "FORT"
        return "NORMAL"

    # =====================================================================================
    # SECTION 2 : LOGIQUE DE DÉCISION
    # =====================================================================================

    # === AMÉLIORATION : CHOIX DE PASSIF CONTEXTUEL ===
    def choisir_passif(self, player_state, available_passives_ids, game_state):
        """Choisit un passif en évaluant leur pertinence dans la situation actuelle."""
        best_passive = None
        best_score = -1

        for passive_id in available_passives_ids:
            score = 0
            # Évaluer chaque passif disponible
            if passive_id in ["second_chance", "volonte"]:
                if player_state['hp'] < 25: score = 100 # Priorité absolue si bas en HP
                else: score = 50
            
            if passive_id == "mode_facile":
                score = 80 # Toujours un excellent choix pour l'économie
            
            if passive_id == "human_tide":
                # Très fort si on a déjà beaucoup de personnages
                if sum(1 for c in player_state['inventaire'] if c) >= 2: score = 90
                else: score = 60
            
            if passive_id == "a_main_nue":
                score = 75 # Bon passif polyvalent
            
            if passive_id == "vif":
                score = 70
            
            if passive_id == "promotion":
                # Excellent si on a des personnages chers en main
                has_expensive_char = any(c['cout'] >= 6 for c in player_state['inventaire'] if c)
                if has_expensive_char: score = 85
                else: score = 40

            if score > best_score:
                best_score = score
                best_passive = passive_id
        
        if best_passive:
            player_state['passives'][best_passive] = True
            logging.info(f"[IA LOG - Passif] L'IA a choisi : {best_passive} (Score: {best_score}, Tour {game_state['tour']})")
            return

    

    def choisir_personnage_invocation(self, choices, player_state, opponent_state, game_state):
        """L'IA choisit le personnage le plus pertinent parmi les 3 options en utilisant le scoring."""
        if not choices: return None
        
        danger = self.analyser_situation(player_state, opponent_state)
        
        # Utilise la fonction de scoring améliorée pour trouver le meilleur personnage
        best_char = max(choices, key=lambda char: self.scorer_personnage(char, player_state, opponent_state, danger))
        
        score = self.scorer_personnage(best_char, player_state, opponent_state, danger)
        logging.info(f"[IA LOG - Invocation] L'IA a choisi d'invoquer {best_char['nom']} (Score: {score:.2f})")
        return best_char

    def placer_strategiquement(self, player_state, opponent_state, game_state):
        """Décide quel personnage placer sur le terrain en se basant sur le meilleur score de pertinence."""
        placeable = [char for char in player_state['inventaire'] if char and "Fatigue d'invocation" not in char.get("statuts", [])]
        if not placeable: return False
        
        danger = self.analyser_situation(player_state, opponent_state)
        
        # Sélectionne le meilleur personnage à placer en se basant sur le scoring global
        best_char_to_place = max(placeable, key=lambda c: self.scorer_personnage(c, player_state, opponent_state, danger))
        
        if player_state['terrain']:
            current_char = player_state['terrain']
            current_score = self.scorer_personnage(current_char, player_state, opponent_state, danger)
            new_score = self.scorer_personnage(best_char_to_place, player_state, opponent_state, danger)
            
            # Le seuil de +20 évite les changements inutiles, c'est une excellente idée
            if new_score > current_score + 20:
                idx = player_state['inventaire'].index(best_char_to_place)
                player_state['inventaire'][idx] = current_char
                player_state['terrain'] = best_char_to_place
                logging.info(f"[IA LOG - Placement] Remplacement : {best_char_to_place['nom']} remplace {current_char['nom']}")
                return True
            return False
        else:
            idx = player_state['inventaire'].index(best_char_to_place)
            player_state['inventaire'][idx] = None
            player_state['terrain'] = best_char_to_place
            logging.info(f"[IA LOG - Placement] Placement initial : {best_char_to_place['nom']}")
            return True

    # === AMÉLIORATION MAJEURE : UTILISATION DE CAPACITÉ BASÉE SUR LES TAGS ===
    # Dans ton fichier AITrainer

# === AMÉLIORATION MAJEURE : UTILISATION DE CAPACITÉ BASÉE SUR LES TAGS ET LES PRÉREQUIS ===
    def utiliser_capacite_smart(self, player_state, opponent_state, game_state):
        """
        Utilise une capacité en évaluant ses tags, le contexte ET les prérequis de base.
        """
        usable = []
        all_chars = [(i, char) for i, char in enumerate(player_state['inventaire'])]
        if player_state['terrain']:
            all_chars.append(("terrain", player_state['terrain']))

        for slot, char in all_chars:
            if char and "capacite" in char and player_state['pr'] >= char['capacite']['cout']:
                usable.append((slot, char, char['capacite']))
        
        if not usable: return None
        
        danger = self.analyser_situation(player_state, opponent_state)
        opponent_status = self.evaluer_etat_adversaire(opponent_state)
        
        best_choice = None
        best_priority = 10 # Seuil minimum pour agir

        for slot, char, capacite in usable:
            priority = 0
            tags = capacite.get('tags', [])

            # =====================================================================
            # NOUVELLE LOGIQUE DE VÉRIFICATION DES PRÉREQUIS
            # =====================================================================
            # Si la capacité applique un statut simple, vérifier si le personnage l'a déjà.
            status_map = {
                "Cible": "En chasse", "Attaque surprise": "À l'affût", "Boule de feu": "Incantation",
                "Petit effort": "Sommeil", "Bouclier coton": "Coton", "Pluie battante": "Parapluie",
                "Contre-attaque": "Contre", "Souvenir inoubliable": "Cadeau de Noël", "Bourrasque": "Typhon",
                "Spores": "Champignon", "Monologue ennuyeux": "blablabla", "Vol": "Vol", "Nuisible": "Malicieux",
                "Gros câlin": "Calin", "Bourdonnement": "Bourdonnement", "Piratage": "Piratage"
            }
            if capacite['nom'] in status_map:
                status_to_add = status_map[capacite['nom']]
                if status_to_add in char.get("statuts", []):
                    logging.info(f"[IA DEBUG - Capacité] Rejet de {capacite['nom']} : statut déjà présent.")
                    continue # Passe à la capacité suivante, ne la considère même pas.

            # Cas spécifique pour "Evolution"
            if capacite['nom'] == "Evolution":
                if None not in player_state['inventaire']:
                    logging.info(f"[IA DEBUG - Capacité] Rejet de {capacite['nom']} : inventaire plein.")
                    continue

            # =====================================================================
            # Évaluation basée sur les tags (inchangée)
            # =====================================================================
            if 'heal' in tags or 'defense' in tags:
                if danger > 50: priority = 80
            
            if 'offensif' in tags or 'buff_self' in tags:
                if danger < 40: priority = 70
                else: priority = 30
            
            if 'direct_damage' in tags:
                if opponent_status == "FAIBLE": priority = 95
            
            if 'debuff' in tags or 'control' in tags:
                if opponent_state.get('terrain'): priority = 50
            
            # Ajout d'une priorité pour les capacités d'invocation
            if 'summon' in tags:
                priority = 70

            # Ajustements
            if capacite['cout'] > player_state['pr'] / 2: priority -= 20

            logging.info(f"[IA DEBUG - Capacité] Évaluation de {capacite['nom']} (Tags: {tags}): Priorité {priority}")

            if priority > best_priority:
                best_priority = priority
                best_choice = (slot, char, capacite)
        
        if best_choice:
            logging.info(f"[IA LOG - Capacité] Demande d'utilisation de {best_choice[2]['nom']} (Priorité: {best_priority})")
            return best_choice
        
        return None
    
    # Dans cogs/ai_trainer.py, à l'intérieur de la classe AITrainer

    # =====================================================================================
    # SECTION 3 : EXÉCUTION DU TOUR COMPLET
    # =====================================================================================
    async def execute_turn(self, manager_cog, player_state, opponent_state, game_state):
        """
        Contient toute la logique de décision de l'IA Apprenti pour un tour de préparation.
        C'est le code qui a été déplacé depuis game_1v1_manager.py.
        """
        logging.info(f"[IA APPRENTI - STRATÉGIE] Exécution du tour {game_state['tour']}.")

        if game_state['tour'] == 1:
            # --- STRATÉGIE SPÉCIALE TOUR 1 : AGRESSIVE ET DIRECTE ---
            if player_state['pr'] > 0 and None in player_state['inventaire']:
                choices = manager_cog._generate_invocation_choices(player_state)
                if choices:
                    char_to_invoke = self.choisir_personnage_invocation(choices, player_state, opponent_state, game_state)
                    if char_to_invoke and char_to_invoke['cout'] <= player_state['pr']:
                        char_data = copy.deepcopy(char_to_invoke)
                        if 'pv_max' not in char_data:
                            char_data['pv_max'] = char_data['pv']
                        
                        player_state['pr'] -= char_data['cout']
                        empty_slot = player_state['inventaire'].index(None)
                        player_state['inventaire'][empty_slot] = char_data
                        logging.info(f"[IA APPRENTI - ACTION T1] Invocation de {char_data['nom']}")

            self.placer_strategiquement(player_state, opponent_state, game_state)

        else:
            # --- STRATÉGIE STANDARD (POUR LES TOURS 2 ET PLUS) ---
            chosen_ability_data = self.utiliser_capacite_smart(player_state, opponent_state, game_state)
            if chosen_ability_data:
                slot, char, capacite = chosen_ability_data
                
                actual_cost = capacite['cout']
                # Note : La logique 'promotion' et 'maitre_capacites' est gérée dans le manager,
                # mais on la garde ici pour une IA autonome si besoin.
                if 'promotion' in player_state.get('passives', {}):
                    if char.get('cout', 0) in [6, 7, 8]: actual_cost = 1
                
                is_free_cast = False
                if ('maitre_capacites' in player_state.get('passives', {}) and
                    player_state.get('ability_usage_counter', 0) == 2):
                    actual_cost = 0
                    is_free_cast = True

                if player_state['pr'] >= actual_cost:
                    player_state['pr'] -= actual_cost
                    logging.info(f"[IA APPRENTI - ACTION] Utilise la capacité {capacite['nom']} pour {actual_cost} PR.")
                    # On appelle la méthode du manager en utilisant le paramètre 'manager_cog'
                    await manager_cog._execute_ai_ability_effect(player_state, opponent_state, slot, char, capacite, actual_cost, is_free_cast)

            self.placer_strategiquement(player_state, opponent_state, game_state)

            # Dans cogs/ai_trainer.py, dans la méthode execute_turn

            # ... (après le bloc de placement)

            if player_state['pr'] > 0 and None in player_state['inventaire']:
                choices = manager_cog._generate_invocation_choices(player_state)
                if choices:
                    char_to_invoke = self.choisir_personnage_invocation(choices, player_state, opponent_state, game_state)
                    if char_to_invoke and char_to_invoke['cout'] <= player_state['pr']:
                        char_data = copy.deepcopy(char_to_invoke)
                        if 'pv_max' not in char_data:                            char_data['pv_max'] = char_data['pv']
                        
                        # === BLOC CORRIGÉ ===
                        if 'a_main_nue' in player_state.get('passives', {}):
                            char_data['pv'] += 5
                            char_data['pv_max'] += 5
                            if "statuts" not in char_data:
                                char_data["statuts"] = []
                            char_data["statuts"].append("À main nue")
                        
                        # La même correction ici pour la fatigue
                        if game_state['tour'] > 1:
                            if "statuts" not in char_data:
                                char_data["statuts"] = []
                            char_data["statuts"].append("Fatigue d'invocation")
                        # === FIN DU BLOC CORRIGÉ ===
                        
                        player_state['pr'] -= char_data['cout']
                        empty_slot = player_state['inventaire'].index(None)
                        player_state['inventaire'][empty_slot] = char_data
                        logging.info(f"[IA APPRENTI - ACTION] Invocation de {char_data['nom']}")


async def setup(bot):
    """Fonction requise par Discord.py pour charger le cog."""
    pass