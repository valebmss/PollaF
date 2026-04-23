from django import template

register = template.Library()

# FIFA 3-letter → ISO 2-letter (lowercase) for flagcdn.com
_FIFA_ISO = {
    'MEX':'mx','RSA':'za','KOR':'kr','CZE':'cz',
    'CAN':'ca','BIH':'ba','QAT':'qa','SUI':'ch',
    'BRA':'br','MAR':'ma','HAI':'ht','SCO':'gb-sct',
    'USA':'us','PAR':'py','AUS':'au','TUR':'tr',
    'GER':'de','CUW':'cw','CIV':'ci','ECU':'ec',
    'NED':'nl','JPN':'jp','SWE':'se','TUN':'tn',
    'BEL':'be','EGY':'eg','IRN':'ir','NZL':'nz',
    'ESP':'es','CPV':'cv','KSA':'sa','URU':'uy',
    'FRA':'fr','SEN':'sn','IRQ':'iq','NOR':'no',
    'ARG':'ar','ALG':'dz','AUT':'at','JOR':'jo',
    'POR':'pt','COD':'cd','UZB':'uz','COL':'co',
    'ENG':'gb-eng','CRO':'hr','GHA':'gh','PAN':'pa',
}


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def saved_in_group(predicciones_map, partidos_list):
    return sum(1 for p in partidos_list if p.id in predicciones_map)


@register.filter
def flag_url(pais):
    """Returns flagcdn.com URL for a Pais object."""
    if not pais:
        return ''
    iso = _FIFA_ISO.get(pais.codigo, '')
    if not iso:
        return ''
    return f'https://flagcdn.com/24x18/{iso}.png'


@register.filter
def puntos_color(puntos):
    if puntos == 5: return '#155724'
    if puntos == 2: return '#856404'
    if puntos == 0: return '#721c24'
    return '#aaa'


@register.filter
def puntos_bg(puntos):
    if puntos == 5: return '#d4edda'
    if puntos == 2: return '#fff3cd'
    if puntos == 0: return '#f8d7da'
    return '#f4f4f4'


@register.filter
def puntos_icono(puntos):
    if puntos == 5: return '★ 5pts'
    if puntos == 2: return '~ 2pts'
    if puntos == 0: return '✗ 0pts'
    return ''
