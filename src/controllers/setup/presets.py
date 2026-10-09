from flask import request, session, jsonify, abort
from src.controllers.setup import bp_setup, VALID_CULTURES, VALID_TYPES
from src.controllers.setup.validation import validate_bins
from src.core.user_presets import list_presets, save_preset, delete_preset, update_preset


@bp_setup.route('/<culture>/<rtype>/presets', methods=['GET', 'POST'])
@bp_setup.route('/<culture>/<rtype>/presets/<preset_id>', methods=['PUT'])
def personal_presets(culture, rtype, preset_id=None):
    if culture not in VALID_CULTURES or rtype not in VALID_TYPES:
        abort(404)
    if not session.get('user'):
        return jsonify(message='Faça login para acessar seus presets.'), 401
    owner = session['user']['id']
    if request.method == 'GET':
        return jsonify(presets=list_presets(owner, culture, rtype))
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError('Envie um objeto JSON.')
        name = data.get('name')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError('Informe um nome de 1 a 80 caracteres.')
        # Reutiliza as mesmas regras de intervalos aceitas pela geração.
        bins = validate_bins(data.get('bins'), culture, rtype)
        if request.method == 'PUT':
            if not update_preset(owner, culture, rtype, preset_id, name.strip(), bins):
                abort(404)
        else:
            preset_id = save_preset(owner, culture, rtype, name.strip(), bins)
    except (ValueError, TypeError) as error:
        return jsonify(message=str(error)), 400
    return jsonify(id=preset_id, message='Preset salvo.'), 200 if request.method == 'PUT' else 201


@bp_setup.delete('/presets/<preset_id>')
def remove_personal_preset(preset_id):
    if not session.get('user'):
        return jsonify(message='Faça login para acessar seus presets.'), 401
    if not delete_preset(session['user']['id'], preset_id):
        abort(404)
    return jsonify(message='Preset excluído.')
