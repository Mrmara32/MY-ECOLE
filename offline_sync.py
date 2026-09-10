"""
Support du mode hors-ligne cote serveur.

Le principe : une action faite hors-ligne (inscrire un eleve, encaisser un
versement) est mise en file d'attente dans le navigateur avec une cle unique
(client_op_id, generee par crypto.randomUUID() cote client). Des que la
connexion revient, cette action est envoyee au serveur avec sa cle.

Le decorateur @idempotent protege contre le double-traitement si la meme
requete arrive deux fois -- par exemple si la reponse du serveur n'a pas pu
etre recue par le navigateur avant une nouvelle coupure, et que la
synchronisation retente l'envoi au retour de connexion. Sans cette protection,
un versement pourrait etre encaisse deux fois, ou un eleve inscrit deux fois.
"""
import json
from functools import wraps
from flask import request, jsonify, g

from database import db


def idempotent(endpoint_name):
    def decorateur(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            body = request.get_json(silent=True) or {}
            client_op_id = body.get('client_op_id')
            if not client_op_id:
                # Appel normal (en ligne, sans cle) : comportement inchange.
                return f(*args, **kwargs)

            existant = db.execute(
                "SELECT response_body, response_status FROM idempotency_keys WHERE client_op_id=?",
                (client_op_id,),
            ).fetchone()
            if existant:
                # Deja traite precedemment : on renvoie la meme reponse, sans rejouer l'operation.
                return jsonify(json.loads(existant['response_body'])), existant['response_status']

            resultat = f(*args, **kwargs)
            response, status = (resultat if isinstance(resultat, tuple) else (resultat, 200))[:2]

            try:
                corps = response.get_json()
                db.execute(
                    "INSERT INTO idempotency_keys (client_op_id,ecole_id,endpoint,response_body,response_status) "
                    "VALUES (?,?,?,?,?)",
                    (client_op_id, g.user['ecole_id'], endpoint_name, json.dumps(corps), status),
                )
                db.commit()
            except Exception:
                # L'enregistrement de la cle ne doit jamais empecher de renvoyer la vraie reponse.
                pass

            return resultat
        return wrapper
    return decorateur
