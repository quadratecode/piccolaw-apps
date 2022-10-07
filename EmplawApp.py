from pywebio import *
from pywebio.session import info as session_info
from dateutil.easter import *
import arrow
import plotly.express as px
import pandas as pd
import copy
import portion
from pyecharts.components import Table

# §§
# LICENSE: https://github.com/quadratecode/piccolaw-apps/blob/master/LICENSE.md
# §§

# Custom config
config(title="Web App Arbeitsrecht | Web App Employment Law",
      description="Berechne Kündigungs-, Sperr- und Lohnfortzahlungsfristen | Calculate embargo, sick pay and notice periods",
      css_file = "https://www.piccolaw.ch/pl_apps.css", # adjust for personal CSS
      theme = "default") 


# --- FUNCTIONS --- #

# Function to choose language according to browser language
def lang(eng, german):
    if 'de' in session_info.user_language:
        return german
    else:
        return eng

# Validate employment form
def check_form_employment(data):
    try: 
        arrow.get(data["employment_sdt"], "DD.MM.YYYY")
    except:
        return ("employment_sdt", lang("ERROR: Invalid date", "ERROR: Ungültiges Datum"))

def check_case_comb(data):
    if (data["incapacity_type"] == False) and (data["trial_relevance"] == False) and (data["termination_occurence"] == False):
        output.put_error(lang("ERROR: No parameter selected",
                                "ERROR: Kein Parameter ausgewählt"),
                            closable=True,
                            scope="scope_input_instructions")
        return ("", "")

# Validate incap form
# Source: https://stackoverflow.com/a/72292729/14819955
def check_form_incapacity(data):
    required_pairs = {1} # Specify all the required pairs in this set
    max_pairs = 3        # Max numbber of pairs
    data_lst = []

    for key in data.keys():
        if data[key] != "":
            try: 
                arrow.get(data[key], "DD.MM.YYYY")
            except:
                return (key, lang("ERROR: Invalid date", "ERROR: Ungültiges Datum"))

    for i in range(1, max_pairs+1):
        s_key = f"illacc_sdt_{i}"
        e_key = f"illacc_edt_{i}"

        # Get the data from the dict. If the key doesn't exist, treat it as an empty string
        s_val = data.get(s_key, "")
        e_val = data.get(e_key, "")

        if i in required_pairs or s_val or e_val:
            if i in required_pairs: 
                # This is a required pair and input is missing
                if not s_val:
                    output.put_error(
                        lang("ERROR: Uneven number of dates.",
                        "ERROR: Ungerade Anzahl Daten."),
                        closable=True,
                        scope="scope_input_instructions")
                    return ("", "")
                elif not e_val:
                    output.put_error(lang("ERROR: Uneven number of dates.",
                        "ERROR: Ungerade Anzahl Daten."),
                        closable=True,
                        scope="scope_input_instructions")
                    return ("", "")
            elif e_val and not s_val:
                # e_key is specified but not s_key
                output.put_error(
                    lang("ERROR: Uneven number of dates.",
                    "ERROR: Ungerade Anzahl Daten."),
                    closable=True,
                    scope="scope_input_instructions")
                return ("", "")
            elif s_val and not e_val:
                # s_key is specified but not e_key
                output.put_error(
                    lang("ERROR: Uneven number of dates.",
                    "ERROR: Ungerade Anzahl Daten."),
                    closable=True,
                    scope="scope_input_instructions")
                return ("", "")
            
            # Data is valid
            data_lst.append(arrow.get(data[s_key], "DD.MM.YYYY"))
            data_lst.append(arrow.get(data[e_key], "DD.MM.YYYY"))

    data_lst_sorted = sorted(data_lst)
    if data_lst_sorted != data_lst:
        output.put_error(lang("ERROR: Dates not in chronological order",
                                "ERROR: Daten nicht in chronologischer Abfolge"),
                            closable=True,
                            scope="scope_input_instructions")
        return ("", "")

# Validate trial from
def check_trial(data):
    if len(data["workdays_input"]) < 1:
        output.put_error(lang("ERROR: No days selected", "ERROR: Keine Arbeitstage ausgewählt"),
                            closable=True,
                            scope="scope_input_instructions")
        return ("", "")

# Validate termination form
def check_form_termination(data):
    try: 
        arrow.get(data["termination_dt"], "DD.MM.YYYY")
    except:
        return ("termination_dt", lang("ERROR: Invalid date", "ERROR: Ungültiges Datum"))
    if employment_sdt > arrow.get(data["termination_dt"], "DD.MM.YYYY"):
        output.put_error(lang("ERROR: Termination date cannot be older than the employment start date. Start date: " + str(employment_sdt.format("DD.MM.YYYY")) ,
                                "ERROR: Das Kündigungsdatum kann nicht vor dem Startdatum liegen. Startdatum: " + str(employment_sdt.format("DD.MM.YYYY"))),
                            closable=True,
                            scope="scope_input_instructions")
        return ("", "")

# Function to correct date subtraction if origin month has more days than target month
# See issue 1
def subtract_corr(sdt, edt):
    if sdt.day != edt.day:
        return(edt)
    else:
        edt = edt.shift(days=-1)
        return(edt)

# Function to calculate overlap between two date ranges
def overlap_calc(sdt_1, sdt_2, edt_1, edt_2):
        latest_start = max(sdt_1, sdt_2)
        earliest_end = min(edt_1, edt_2)
        delta = (earliest_end.date() - latest_start.date()).days + 1
        overlap = max(0, delta)
        return(overlap)

# Function to grow date interval
def grow(main, gaps):
    start, end = main
    for lo, hi in gaps:
        if hi < start:
            # gap is lower than main
            continue
        if lo > end:
            # gap is higher than main
            break
        # extend main end by overlap length
        overlap_length = overlap_calc(start, lo, end, hi)
        end = max(end, hi)
        end = end.shift(days=overlap_length)
    return [start, end]

# Function to flatten list
# Source: https://stackoverflow.com/a/71468284/14819955
def flat(x):
    match x:
        case []:
            return []
        case [[*sublist], *r]:
            return [*sublist, *flat(r)]

# Function to remove empty nested lists
# Source: https://stackoverflow.com/a/20368240/14819955
def purify(lst):
    for (i, sl) in enumerate(lst):
        if type(sl) == list:
            lst[i] = purify(sl)
    return [i for i in lst if i != [] and i != '']

# Function to push dates to desired endpoint
def push_endpoint(date, endpoint):
    if endpoint in ["No mention of termination date", "Keine Angaben zum Kündigungstermin", "Termination date only end of month", "Kündigungstermin nur auf Ende Monat"]:
        return date.ceil("month") # push to the end of the month
    elif endpoint in ["Termination date only end of week", "Kündungstermin nur auf Ende Woche"]:
        return date.ceil("week") # push to the end of the week
    elif endpoint in ["Termination date only end of quarter", "Kündungstermin nur auf Ende Quartal"]:
        return date.ceil("quarter") # push to the end of the quarter
    elif endpoint in ["Termination date only end of year", "Kündungstermin nur auf Ende Jahr"]:
        return date.ceil("year") # push to the end of the year
    else:
        return date

# Function to evaluate service year thresholds
def get_last_index(list_of_elems, condition, default_idx=-1) -> int:
    try:
        return next(i for i in range(len(list_of_elems) - 1, -1, -1)
                    if condition(list_of_elems[i]))
    except StopIteration:  # no date earlier than comparison date is found
        return default_idx

# Function to calculate time period duration in days
def period_duration(start_date, end_date):
    return (end_date - start_date).days + 1
    
# Function to correct single dates
def single_date(lst, first_index, last_index):
    if lst[first_index] > lst[last_index]:
        lst[first_index] = lst[last_index]
        return lst

# Function to check if index exists, if not place empty string
def check_index(lst, index):
    if index < len(lst):
        return lst[index]
    else:
        lst.insert(index, "")
        return lst[index]

# Function to populate dict key with sublist of pairs
def populate_dct(in_dct):
    paired_lst = []
    # New dict without empty keys, convert others to arrow object
    new_dct = {}
    for key, value in in_dct.items():
        if in_dct[key] != "":
            new_dct[key] = arrow.get(value, "DD.MM.YYYY")
    # Put values into list
    value_lst = list(new_dct.values())
    while value_lst:
        paired_lst.append(value_lst[:2])
        value_lst = value_lst[2:]
    return paired_lst

# Function to merge overlapping date ranges
def merge(lst):
    # Do not merge empty lits
    if lst != []:
        intervals = [portion.closed(a, b) for a, b in lst]
        merge = portion.Interval(*intervals)
        merge = [[i.lower, i.upper] for i in merge]
        # Hotfix for rare error where inf is returned (investigate)
        if merge != [[portion.inf, -portion.inf]]:
            return merge
        else:
            return lst
    else:
        return lst

# Function to check if a given date is a holiday
# Source: https://www.bj.admin.ch/dam/bj/de/data/publiservice/service/zivilprozessrecht/kant-feiertage.pdf
def holiday_checker(day, workplace):
    easter_dt = arrow.Arrow.fromdate(easter(day.year))
    if (
        # Neujahrstag (all cantons)
        (day == arrow.Arrow(day.year, 1, 1))
        # Berchtoldstag
        or (day == arrow.Arrow(day.year, 1, 2) and workplace in ["ZH", "BE", "LU", "OW", "NW", "GL", "ZG", "FR", "SO", "SH", "SG", "AG", "TG", "VD", "VS", "NE", "JU"])
        # Heilige Drei Könige
        or (day == arrow.Arrow(day.year, 1, 6) and workplace in ["UR", "SZ", "TI"])
        # Jahrestag der Ausrufung der Republik Neuenburg
        or (day == arrow.Arrow(day.year, 3, 1) and workplace in ["NE"])
        # Josefstag
        or (day == (arrow.Arrow(day.year, 3, 19) and workplace in ["UR", "SZ", "NW", "SO", "TI", "VS"]))
        # Karfreitag
        or (day == easter_dt.shift(days=-2) and workplace in ["ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "FR", "SO", "BS", "BL", "SH", "AR", "AI", "SG", "GR", "AG", "TG", "VD", "NE", "GE", "JU"])
        # Ostermontag
        or (day == easter_dt.shift(days=+1) and workplace in ["ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "FR", "SO", "BS", "BL", "SH", "AR", "AI", "SG", "GR", "AG", "TG", "TI", "VD", "VS", "GE", "JU"])
        # Fahrtsfest
        or (day == arrow.Arrow(day.year, 4, 1).shift(weekday=4) and workplace in ["GL"])
        # Tag der Arbeit
        or (day == arrow.Arrow(day.year, 5, 1) and workplace in ["ZH", "BS", "BL", "SH", "AG", "TG", "TI", "NE", "JU"])
        # Auffahrt
        or (day == easter_dt.shift(days=+39) and workplace in ["ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "FR", "SO", "BS", "BL", "SH", "AR", "AI", "SG", "GR", "AG", "TG", "TI", "VD", "VS", "NE", "GE", "JU"])
        # Pfingstmontag
        or (day == easter_dt.shift(days=+50) and workplace in ["ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "FR", "SO", "BS", "BL", "SH", "AR", "AI", "SG", "GR", "AG", "TG", "TI", "VD", "VS", "GE", "JU"])
        # Frohnleichnam
        or (day == easter_dt.shift(days=+60) and workplace in ["LU", "UR", "SZ", "OW", "NW", "ZG", "FR","SO", "AI", "AG", "TI", "VS", "NE", "JU"])
        # Commémoration du plébiscite jurassien
        or (day == arrow.Arrow(day.year, 6, 23) and workplace in ["JU"])
        # Peter und Paul
        or (day == arrow.Arrow(day.year, 6, 29) and workplace in ["TI"])
        # Bundesfeier (all cantons)
        or (day == arrow.Arrow(day.year, 8, 1))
        # Mariä Himmelfahrt
        or day == (arrow.Arrow(day.year, 8, 15) and workplace in ["LU", "UR", "SZ", "OW", "NW", "ZG", "FR", "SO", "AI", "AG", "TI", "VS", "JU"])
        # Jeûne genevois
        or (day == arrow.Arrow(day.year, 9, 1).shift(weekday=6).shift(weekday=3) and workplace in ["GE"])
        # Lundi du Jeûne
        or day == (arrow.Arrow(day.year, 9, 1).shift(weekday=6).shift(days=+7).shift(days=+8) and workplace in ["VD"])
        # Mauritiustag
        or (day == arrow.Arrow(day.year, 9, 25) and workplace in ["AI"])
        # Bruderklausenfest
        or (day == arrow.Arrow(day.year, 9, 25) and workplace in ["OW"])
        # Allerheiligen
        or (day == arrow.Arrow(day.year, 11, 1) and workplace in ["LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "FR", "SO", "AI", "SG", "AG", "TI", "VS", "JU"])
        # Mariä Empfängnis
        or (day == arrow.Arrow(day.year, 12, 8) and workplace in ["LU", "UR", "SZ", "OW", "NW", "ZG", "FR", "AI", "AG", "TI", "VS"])
        # Weihnachtstag (all cantons)
        or (day == arrow.Arrow(day.year, 12, 25))
        # Stephanstag
        or (day == arrow.Arrow(day.year, 12, 26) and workplace in ["ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "FR", "BS", "BL", "SH", "AR", "AI", "SG", "GR", "AG", "TG", "TI", "VS", "NE"])
        # Restauration de la République
        or (day == arrow.Arrow(day.year, 12, 31) and workplace in ["GE"])
    ):
        return True
    else:
        return False

# Function to limit a date to be between lower and upper bounds
# Source: https://stackoverflow.com/a/5996949/14819955
def clamp(n, minn, maxn):
    if n < minn:
        return minn
    elif n > maxn:
        return maxn
    else:
        return n

# Control bar functions
def btn_click(btn_val):
    if btn_val == "< Back to piccolaw.ch":
        session.run_js('window.location = "https://www.piccolaw.ch/"')
    elif btn_val == "Restart App":
        session.run_js('window.location.reload()')
    elif btn_val == "Feedback":
        session.run_js('open("mailto:hello@piccolaw.ch")')


# --- MAIN FNCTION --- #
def emplaw_app():

    # --- SESSION CONTROL --- #
    session.set_env(input_panel_fixed=False,
                    output_animation=False)

    # --- INPUT --- #

    output.put_buttons(
        ["< Back to piccolaw.ch", "Restart App", "Feedback"],
        small=True,
        onclick=btn_click)
        
    output.put_markdown(lang("""
        # Web App Employment Law
        `v1.2.1-beta.3 | Updated: 2022-09-28`
        """,
        """
        # Web App Arbeitsrecht
        `v1.2.1-beta.3 | Updated: 2022-09-28`
        """))

    # User info: Landing page
    with output.use_scope("scope_input_instructions"):
        output.put_markdown(lang("""
            Possible evaluations:
            - Trial period extensions
            - Notice periods
            - Embargo periods
            - Sick pay claim
            - Validity of termination
            ----
            - Screenwidth >1080p recommended, JavaScript required
            - Language is set according to your browser settings (DE/EN)
            - Source on [GitHub](https://github.com/quadratecode/pl-emplaw-app)
            ""","""
            Mögliche Berechnungen:
            - Verlängerung der Probezeit
            - Kündigungsfristen
            - Sperrfristen
            - Anspruch auf Lohnfortzahlung
            - Gültigkeit Kündigung
            ----
            - Bildschrimvertikale > 1080p empfohlen, JavaScript erforderlich
            - Die Sprache richtet sich nach den Browsereinstellungen (DE/EN)
            - Quellcode auf [GitHub](https://github.com/quadratecode/pl-emplaw-app)
            """)).style('margin-top: 20px')

        output.put_collapse(lang("Legal Framework", "Rechtliche Grundlagen",), [
            output.put_html(lang("""
                <ul>
                    <li> Probation period: <a target="_blank" rel="noopener noreferrer" href="https://www.fedlex.admin.ch/eli/cc/27/317_321_377/en#art_335_b">Art. 335b OR</a> </li>
                    <li> Regular termination: <a target="_blank" rel="noopener noreferrer" href="https://www.fedlex.admin.ch/eli/cc/27/317_321_377/en#art_335_c">Art. 335c OR</a> </li>
                    <li> Embargo period: <a target="_blank" rel="noopener noreferrer" href="https://www.fedlex.admin.ch/eli/cc/27/317_321_377/en#art_336_c">Art. 336c OR</a> </li>
                    <li> Sick pay: <a target="_blank" rel="noopener noreferrer" href="https://www.fedlex.admin.ch/eli/cc/27/317_321_377/en#art_324_a">Art. 324a OR</a> </li>
                    <li> Federal document on legally mandated holidays: <a target="_blank" rel="noopener noreferrer" href="https://www.bj.admin.ch/dam/bj/de/data/publiservice/service/zivilprozessrecht/kant-feiertage.pdf">Link to PDF</a> </li>
                </ul>
            """,
            """
                 <ul>
                    <li> Probezeit: <a target="_blank" rel="noopener noreferrer" href="https://www.fedlex.admin.ch/eli/cc/27/317_321_377/de#art_335_b">Art. 335b OR</a> </li>
                    <li> Ordentliche Kündigung: <a target="_blank" rel="noopener noreferrer" href="https://www.fedlex.admin.ch/eli/cc/27/317_321_377/de#art_335_c">Art. 335c OR</a> </li>
                    <li> Sperrfristen: <a target="_blank" rel="noopener noreferrer" href="https://www.fedlex.admin.ch/eli/cc/27/317_321_377/de#art_336_c">Art. 336c OR</a> </li>
                    <li> Lohnfortzahlung: <a target="_blank" rel="noopener noreferrer" href="https://www.fedlex.admin.ch/eli/cc/27/317_321_377/de#art_324_a">Art. 324a OR</a> </li>
                    <li> Dokument des Bundes über die gesetzlichen Feiertage: <a target="_blank" rel="noopener noreferrer" href="https://www.bj.admin.ch/dam/bj/de/data/publiservice/service/zivilprozessrecht/kant-feiertage.pdf">Link to PDF</a> </li>
                </ul>
            """))]).style('margin-top: 20px')

        output.put_markdown(lang("""
            ### Terms and Conditions

            This app is provided as is. Use at your own risk. Warranties or liabilities of any kind are excluded to the extent permitted by applicable law. Do not rely solely on the automatically generated evaluation.

            By continuing you agree to these terms.
            ""","""
            ### Nutzungsbedingungen

            Diese App wird im Ist-Zustand und kostenlos zur Verfügung gestellt. Die Nutzung erfolgt auf eigene Gefahr und unter Ausschluss jeglicher Haftung, soweit gesetzlich zulässig. Verlassen Sie sich nicht ausschliesslich auf das automatisch generierte Ergebnis.
            
            Durch weitere Nutzung dieser App stimmst du diesen Nutzungsbedingungen zu.
            """))
    
    # Terms and conditions
    input.actions(lang("Agree and continue?", "Zustimmen und fortfahren?"), [
        {'label': "Okay!", 'value': 'continue'},
    ])

    with output.use_scope("scope_progress"):
        output.put_processbar("bar", init=0, scope="scope_progress", position=0).style('margin-top: 30px')
        output.set_processbar("bar", 0.1)

    # User Info: Employment data (block required)
    with output.use_scope("scope_input_instructions", clear=True):
        output.put_markdown(lang("""
            ### Employment

            Please enter the date of the first day of work and the place of work.

            Notes:
            - The first day of work can be different from the starting date of the employment contract.
            - The first day fully available to the parties counts as first day of work.
            - Format for all date inputs: DD.MM.YYYY (e.g. 01.01.2020, 16.05.2020, 07.12.2020)
            ""","""
            ### Arbeitsverhältnis

            Bitte trage das Datum des Stellenantritts und den Arbeitsort ein.

            Hinweise:
            - Der Tag des Stellenantritts kann vom Anfangsdatum des Arbeitsvertrags abweichen.
            - Als Tag des Stellenatritts gilt der vollumfänglich verfügbare, erste Arbeitstag
            - Format für alle Datumsangaben: DD.MM.YYYY (bspw. 01.01.2020, 16.05.2020, 07.12.2020).
            """))

    # User Input: Employment data (block required)
    employment_data = input.input_group("", [
        input.input(
            lang(
                "First day of work (DD.MM.YYYY)",
                "Tag des Stellenatritts (DD.MM.YYYY)"),
            name="employment_sdt",
            type=input.TEXT,
            required=True,
            pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
            maxlength="10",
            minlength="10",
            placeholder="DD.MM.YYYY"),
        input.select(
            lang("Place of work (canton)", "Arbeitsort (Kanton)"),
            ["AG", "AI", "AR", "BS", "BL", "BE", "FR", "GE", "GL", "GR", "JU", "LU", "NE", "NW",
            "OW", "SH", "SZ", "SO", "SG", "TG", "TI", "UR", "VS", "VD", "ZG", "ZH"],
            name="workplace",
            type=input.TEXT,
            required=True),
    ], validate = check_form_employment)
    # Variables: Employment data (input required)
    # Make employment start date global for validation
    global employment_sdt
    employment_sdt = arrow.get(employment_data["employment_sdt"], "DD.MM.YYYY")
    workplace = employment_data["workplace"]

    output.set_processbar("bar", 0.2)

    # User info: Case combinations (block required)
    with output.use_scope("scope_input_instructions", clear=True):
        output.put_markdown(lang("""
            ### Case Combination

            Please select any case options you would like to evaluate.

            Notes:
            - Performing an evaluation of the trial period is especially advised whenever an incapacity occured during the probation period.
            - The evaluation of a termination is especially advised whenever a termination has already been issued.
            ""","""
            ### Fallkonstellation

            Bitte wähle eine Fallkonstellation aus.

            Hinweise:
            - Die Auswertung der Probezeit ist insb. dann sinnvoll, wenn eine Arbeitsunfähigkeit während der Probezeit aufgetreten ist.
            - Die Auswertung einer Kündigung ist insb. dann sinnvoll, wenn bereits eine Kündigung erfolgt ist.
            """))

    # User input: Case combinations (block required)
    case = input.input_group("", [
        input.select(lang("Type of incapacity", "Art der Arbeitsunfähigkeit"),
            options=[{
                "label":lang("No incapacity","Keine Arbeitsunfähigkeit"),
                "value":False,
                },{
                "label":lang("accident or illness","Unfall oder Krankheit"),
                "value":"illacc",
                },{
                "label":lang("military or civil service", "Militär, Schutz- oder Zivildienst"),
                "value":"milservice"
                },{
                "label":lang("pregnancy", "Schwangerschaft"),
                "value":"preg"}],
            name="incapacity_type",
            inline=True,
            required=True),
        input.select(lang("Evaluation of probation period", "Auswertung Probezeit"),
            options=[{
                    "label":lang("No", "Nein"),
                    "value":False
                    },{
                    "label":lang("Yes", "Ja"),
                    "value":True
                    }],
            name="trial_relevance",
            required=True),
        input.select(lang("Evaluation of termination", "Auswertung Kündigung"),
            options=[{
                    "label":lang("No", "Nein"),
                    "value":False
                    },{
                    "label":lang("Yes", "Ja"),
                    "value":True
                    }],
            name="termination_occurence",
            required=True),
    ], check_case_comb)
    # Get variables
    incapacity_type = case["incapacity_type"]
    trial_relevance = case["trial_relevance"]
    termination_occurence = case["termination_occurence"]
    # Set termination occurence to true if yes
    # Set end of seniority to today if no termination was issued
    if termination_occurence == False:
        termination_dt = arrow.now().shift(years=+3)


    output.set_processbar("bar", 0.3)

    # User info: Amount of incapacities (block optional)
    with output.use_scope("scope_input_instructions", clear=True):
        output.put_markdown(lang("""
            ### Number of Incapacities

            You have chosen to evaluate an incapacity due to illness(es) or accident(s). Please specify how many **seperate** illnesses or accidents are to be evaluated.

            Notes:
            - Incapacities to work count as **seperate** if there is **no connection** between them. Example: There is no connection between having the flu and a car accident – these would count as seperate.
            - Incapacities to work **do not count as seperate** if there is **any connection** between them. For example: A prolonged cancer treatment with multiple periods of absence would count as a single incapacity.
            - Breaks between individual incapacities can be specified in the next step.
            ""","""
            ### Anzahl Arbeitsunfähigkeiten

            Du hast die Auswertung einer Arbeitsunfähigkeit zufolge Krankheit oder Unfall ausgewählt. Bitte spezifiziere, wie viele **unabhängige** Krankheiten oder Unfälle ausgewertet werden sollen.

            Hinweise:
            - Arbeitsunfähigkeiten gelten als **unabhängig**, wenn zwischen ihnen **keinerlei Verbindung** besteht. Beispiel: Es besteht keine Verbindung zwischen einer Grippeerkrankung und einem Autounfall.
            - Arbeitsunfähigkeiten gelten **nicht als unabhängig**, wenn zwischen ihnen eine **irgendwie geartete Verbindung** besteht. Beispiel: Eine langandauernde Krebstherapie mit vielzähligen Abwesenheiten zählt als einzelne Arbeitsunfähigkeit.
            - Unterbrüche zwischen einer einzelnen Arbeitsunfähigkeit können im nächsten Schritt angegeben werden.
            """))

    # User input: Amount of incapacities (block optional)
    if incapacity_type == "illacc":
        illacc_amount = input.select(lang("Number of Seperate Incapacities (Illness or Accident)", "Anzahl unabhängiger Arbeitsunfähigkeiten (Krankheit oder Unfall)"),
            options=[{
                "label":lang("One single accident or illness", "Einzelner Unfall oder Krankheit"),
                "value":1
                },{
                "label":lang("Two seperate accidents or illnesses", "Zwei unabhängige Unfälle oder Krankheiten"),
                "value":2
                },{
                "label":lang("Three seperate accidents or illnesses", "Drei unabhängige Unfälle oder Krankheiten"),
                "value":3}
            ],
            required=True)
    # Set to zero to handle conditions later
    else:
        illacc_amount = 0

    output.set_processbar("bar", 0.4)

    # User info: Trial period (block optional)
    with output.use_scope("scope_input_instructions", clear=True):
        output.put_markdown(lang("""
            ### Probation Period

            Please specify the weekly workdays and the duration of the probation period.

            Notes:
            - Missed workdays during the probation period can lead to its extension.
            - This app respects public holidays and weekends. Other reasons for missed workdays during the probation period are not taken into account.
            ""","""
            ### Angaben Probezeit

            Bitte spezifiziere die Arbeitstage und die Dauer der Probezeit.

            Hinweise:
            - Verpasste Arbeitstage können zu einer Verlängerung der Probezeit führen.
            - Diese App berücksichtigt die Feiertage und Wochenenden im Auswertungszeitraum. Andere Gründe für verpasste Arbeitstage während der Probezeit werden nicht berücksichtigt.
            """))

    # User input: Trial period (block optional)
    if trial_relevance == True:
        trial_period_data = input.input_group("", [
            input.checkbox(
                    lang("Workdays", "Arbeitstage"),
                    ["Montag / Monday", "Dienstag / Tuesday", "Mittwoch / Wednesday", "Donnerstag / Thursday", "Freitag / Friday", "Samstag / Saturday", "Sonntag / Sunday"],
                    name="workdays_input",
                    required=True),
            # probation period
            input.select(
                lang(
                    "Duration of probation period (months)",
                    "Dauer Probezeit (Monate)"),
                    [lang(
                        "No mention of probation period",
                        "Keine Angaben zur Probezeit"),
                        "1", "2", "3",
                    lang(
                        "No probation period",
                        "Keine Probezeit")],
                    name="trial_input",
                    type=input.TEXT,
                    required=True),
        ], validate = check_trial)
        # Declare variables from trial period
        workdays_input = trial_period_data["workdays_input"]
        trial_input = trial_period_data["trial_input"]
        # Set trial relevance to false if no trial period was specified
        if trial_input == lang("No probation period", "Keine Probezeit"):
            trial_relevance = False

        output.set_processbar("bar", 0.5)

    # Intiate incap dictionary
    incap_dct = {}

    # User info: First illacc (alternate block)
    with output.use_scope("scope_input_instructions", clear=True):
        output.put_markdown(lang("""
            ### Incapacity due to Illness or Accident

            You have chosen the evaluation of one or more incapacities due to illness(es) or accident(s).
            For each incapacity (illness or accident) you can specify up to three periods of absence.

            Notes:
            - Enter the periods in chronological order.
            - At least one period must be entered. Leave unused form fields empty.""","""
            ### Arbeitsunfähigkeit zufolge Krankheit oder Unfall

            Du hast die Auswertung einer oder mehreren Arbeitsunfähigkeiten zufolge Krankheit oder Unfall ausgewählt.
            Für jede dieser Arbeitsunfähigkeiten können bis zu drei Absenzperioden spezifiziert werden.

            Hinweise:
            - Trage die einzelnen Perioden in chronologischer Reihenfolge ein.
            - Es muss mindestens eine Periode eingetragen werden. Lasse ungenutzte Formularfelder leer."""))

    # User input: First illacc (alternate block)
    if illacc_amount in [1, 2, 3]:
        first_illacc_data = input.input_group(lang("Incapacity 1", "Arbeitsunfähgkeit 1"), [
            input.input(
                lang(
                    "Period 1 - Start",
                    "Periode 1 - Beginn"),
                name="illacc_sdt_1",
                type=input.TEXT,
                required=True,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            input.input(
                lang(
                    "Period 1 - End",
                    "Periode 1 - Ende"),
                name="illacc_edt_1",
                type=input.TEXT,
                required=True,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            input.input(
                lang(
                    "Period 2 - Start (optional)",
                    "Periode 2 - Beginn (optional)"),
                name="illacc_sdt_2",
                type=input.TEXT,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            input.input(
                lang(
                    "Period 2 - End (optional)",
                    "Periode 2 - Ende (optional)"),
                name="illacc_edt_2",
                type=input.TEXT,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            input.input(
                lang(
                    "Period 3 - Start (optional)",
                    "Periode 3 - Beginn (optional)"),
                name="illacc_sdt_3",
                type=input.TEXT,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            input.input(
                lang(
                    "Period 3 - End (optional)",
                    "Periode 3 - Ende (optional)"),
                name="illacc_edt_3",
                type=input.TEXT,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            ], validate = check_form_incapacity)
        # Sort dates into incap dict as list pairs on the first key
        incap_dct[1] = populate_dct(first_illacc_data)

        output.set_processbar("bar", 0.6)

    # User input: Second illacc (block optional)
    if illacc_amount in [2, 3]:
        second_illacc_data = input.input_group(lang("Incapacity 2", "Arbeitsunfähgkeit 2"), [
            input.input(
                lang(
                    "Start date of first period",
                    "Anfangsdatum der ersten Periode"),
                name="illacc_sdt_1",
                type=input.TEXT,
                required=True,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            input.input(
                lang(
                    "End date of first period",
                    "Enddatum der ersten Periode"),
                name="illacc_edt_1",
                type=input.TEXT,
                required=True,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            input.input(
                lang(
                    "Start date of second period",
                    "Anfangsdatum der zweiten Periode"),
                name="illacc_sdt_2",
                type=input.TEXT,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            input.input(
                lang(
                    "End date of second period",
                    "Enddatum der zweiten Periode"),
                name="illacc_edt_2",
                type=input.TEXT,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            input.input(
                lang(
                    "Start date of third period",
                    "Anfangsdatum der dritten Periode"),
                name="illacc_sdt_3",
                type=input.TEXT,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            input.input(
                lang(
                    "End date of third period",
                    "Enddatum der dritten Periode"),
                name="illacc_edt_3",
                type=input.TEXT,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            ], validate = check_form_incapacity)
        # Sort dates into incap dict as list pairs on the second key
        incap_dct[2] = populate_dct(second_illacc_data)

        output.set_processbar("bar", 0.7)

    # User input: Third illacc (block optional)
    if illacc_amount in [3]:
        third_illacc_data = input.input_group(lang("Incapacity 3", "Arbeitsunfähgkeit 3"), [
            input.input(
                lang(
                    "Start date of first period",
                    "Anfangsdatum der ersten Periode"),
                name="illacc_3_sdt_1",
                type=input.TEXT,
                required=True,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            input.input(
                lang(
                    "End date of first period",
                    "Enddatum der ersten Periode"),
                name="illacc_3_edt_1",
                type=input.TEXT,
                required=True,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            input.input(
                lang(
                    "Start date of second period",
                    "Anfangsdatum der zweiten Periode"),
                name="illacc_3_sdt_2",
                type=input.TEXT,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            input.input(
                lang(
                    "End date of second period",
                    "Enddatum der zweiten Periode"),
                name="illacc_3_edt_2",
                type=input.TEXT,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            input.input(
                lang(
                    "Start date of third period",
                    "Anfangsdatum der dritten Periode"),
                name="illacc_3_sdt_3",
                type=input.TEXT,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            input.input(
                lang(
                    "End date of third period",
                    "Enddatum der dritten Periode"),
                name="illacc_3_edt_3",
                type=input.TEXT,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            ], validate = check_form_incapacity)
        # Sort dates into incap dict as list pairs on the second key
        incap_dct[3] = populate_dct(third_illacc_data)

        output.set_processbar("bar", 0.8)

    # User info: Milservice (alternate block)
    with output.use_scope("scope_input_instructions", clear=True):
        output.put_markdown(lang("""
            ### Militar or Civil Service - Details

            Please specify on which date the service started and on which it ended.

            ""","""
            ### Militär-, Zivil- oder Schutzdienst ###

            Bitte spezifiziere das Start- und Enddatum der Dienstleistung.

            """))


    # User input: Milservice (alternate block)
    if incapacity_type == "milservice":
        milservice_data = input.input_group("", [
            # Start of incapacity
            input.input(
                lang(
                    "Start of service",
                    "Dienstbeginn"),
                    name="milservice_sdt",
                    type=input.TEXT,
                    required=True,
                    pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                    maxlength="10",
                    minlength="10",
                    placeholder="DD.MM.YYYY"),
            # End of incapacity
            input.input(lang(
                "End of service",
                "Dienstende"),
                name="milservice_edt",
                type=input.TEXT,
                required=True,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
        ], validate = check_form_incapacity)
        # Variables: Milservice
        incap_dct[1] = populate_dct(milservice_data)

        output.set_processbar("bar", 0.8)

    # User info: Pregnancy
    with output.use_scope("scope_input_instructions", clear=True):
        output.put_markdown(lang("""
            ### Pregnancy - Details

            Please specify on which date the pregnancy commenced the date of confinement.

            Notes:
            - It is assumed that the requirements for maternity pay according to [Art. 16b EOG](https://www.fedlex.admin.ch/eli/cc/1952/1021_1046_1050/de#art_16_d=) are satisfied.
            - The federal court has decided in BGE 143 III 21 that the pregnancy begins on the day the egg is fertilised.
            - Any natural termination of the pregnancy counts as confinement, including premature birth or miscarriage, not so abortions.
            ""","""
            ### Schwangerschaft - Details

            Bitte spezifiziere das Datum für den Beginn der Schwangerschaft und das Datum der Niederkunft.

            Hinweise:
            - Es wird agenommen, dass die Voraussetzungen für die Entrichtung einer Mutterschaftsentschädigung nach [Art. 16b EOG](https://www.fedlex.admin.ch/eli/cc/1952/1021_1046_1050/de#art_16_d=) erfüllt sind.
            - Das Bundesgericht hat in BGE 143 III 21 entschieden, dass die Schwangerschaft mit der Befruchtung der Eizelle beginnt.
            - Als Niederkunft gilt jede natürliche Befreiung von der Schwangerschaft, d.h. auch Früh- oder Fehlgeburten, nicht aber Schwangerschaftsabbrüche.
            """))

    # User input: Pregnancy
    if incapacity_type == "preg":
        preg_data = input.input_group("", [
            # Start of incapacity
            input.input(
                lang(
                    "Start date of pregnancy",
                    "Datum des Schwangerschaftsbeginns"),
                    name="preg_sdt",
                    type=input.TEXT,
                    required=True,
                    pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                    maxlength="10",
                    minlength="10",
                    placeholder="DD.MM.YYYY"),
            # End of incapacity
            input.input(lang(
                    "Date of confinement",
                    "Datum der Niederkunft"),
                    name="preg_edt",
                    type=input.TEXT,
                    required=True,
                    pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                    maxlength="10",
                    minlength="10",
                    placeholder="DD.MM.YYYY"),
        ], validate = check_form_incapacity)
        # Variables: Pregnancy
        incap_dct[1] = populate_dct(preg_data)

        output.set_processbar("bar", 0.8)

    # User info: Termination (block optional)
    with output.use_scope("scope_input_instructions", clear=True):
        output.put_markdown(lang("""
            ### Termination (by employer)

            Please specify on which date the termination was (or shall be) received, the duration of the notice period and the projected end date of employment.
            
            ""","""
            ### Kündigung (durch Arbeitgeber)

            Bitte spezifiziere das Datum, an dem die Kündigung dem Arbeitnehmer zuging (oder zugehen soll), ferner die Dauer der Kündigungsfrist und den Kündigungstermin.
            
            """))

    # User input: Termination (block optional)
    if termination_occurence == True:
        termination_data = input.input_group("", [
            # Date of termination
            input.input(
                lang(
                    "Date of termination notice receipt",
                    "Datum Kündigungsempfang"),
                name="termination_dt",
                type=input.TEXT,
                required=True,
                pattern="[0-9]{2}\.[0-9]{2}\.(19|20)\d{2}$",
                maxlength="10",
                minlength="10",
                placeholder="DD.MM.YYYY"),
            # Duration of notice period
            input.select(
                lang(
                    "Duration of notice period (months)",
                    "Dauer der Kündigungsfrist (Monate)"),
                [lang(
                    "No mention of notice period",
                    "Keine Angaben zur Kündigungsfrist"),
                    "1", "2", "3", "4", "5", "6", "7", "8","9", "10", "11", "12"],
                name="notice_period_input",
                type=input.TEXT,
                required=True),
            # Cancellation end of month required
            input.select(
                lang(
                    "Termination date",
                    "Kündigungstermin"),
                [lang(
                    "No mention of termination date",
                    "Keine Angaben zum Kündigungstermin"),
                lang(
                    "Termination date only end of week",
                    "Kündungstermin nur auf Ende Woche"),
                lang(
                    "Termination date only end of month",
                    "Kündigungstermin nur auf Ende Monat"),
                lang(
                    "Termination date only end of quarter",
                    "Kündungstermin nur auf Ende Quartal"),
                lang(
                    "Termination date only end of year",
                    "Kündungstermin nur auf Ende Jahr"),
                lang(
                    "Termination date anytime",
                    "Kündungstermin jederzeit")],
                name="endpoint",
                type=input.TEXT,
                required=True),
        ], validate = check_form_termination)
        # Variables: Termination
        termination_dt = arrow.get(termination_data["termination_dt"], "DD.MM.YYYY")
        notice_period_input = termination_data["notice_period_input"]
        endpoint = termination_data["endpoint"]

        output.set_processbar("bar", 0.9)

    # User info: Trial termination (block optional)
    with output.use_scope("scope_input_instructions", clear=True):
        output.put_markdown(lang("""
            ### Probation Period Termination

            You have chosen to evaluate both probation period and termination: Please specify the length of the notice period for the probation period (in days).

            ""","""
            ### Kündigung Probezeit

            Du hast die Auswertung von Kündigung und Probezeit ausgewählt: Bitte spezifiziere die Kündigungsfrist für die Probezeit an (in Tagen).

            """))

    # User input: Trial termination (block optional)
    if (termination_occurence == True) and (trial_relevance == True):
        termination_data = input.input_group("", [
            # Duration of notice period
            input.select(
                lang(
                    "Duration of notice period for probation period (days)",
                    "Dauer der Kündigungsfrist während der Probezeit (Tage)"),
                [lang(
                    "Not specified in contract",
                    "Keine Angaben im Arbeitsvertrag"),
                    "0", "1", "2", "3", "4", "5", "6", "7", "8","9", "10", "11", "12","13", "14", "15",
                    "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30"],
                name="trial_notice_input",
                type=input.TEXT,
                required=True),
        ])
        # Variables: Trial termination
        trial_notice_input = termination_data["trial_notice_input"]

        output.set_processbar("bar", 1)

    # --- DECLARE KNOWN VARIABLES, LISTS, DICTS --- #

    # List structure: unequal indicies indicate start dates, equal ones end dates (starts from index 0)
    # List manipulation is handled in pairs hereafter
    # List for incapacities initiated above

    # Lists and dicts with known input
    reg_employment_lst = [employment_sdt, termination_dt]
    trial_lst = [employment_sdt]

    # List with seniority thresholds
    # Create correponding sick pay dict
    sickpay_dct = {}
    syears = []
    for i in range(0,35):
        syears.append(employment_sdt.shift(years=i))
        # Populate sick pay dict with emtpy lists (used later)
        sickpay_dct[i] = []

    # Empty lists
    notice_period_lst = []
    notice_comp_lst = []
    notice_ext_lst = []
    workdays_num = []
    missed_workdays = []
    repeated_workdays = []
    holidays = []
    embargo_negative = []
    incap_masterlst = []
    embargo_masterlst = []
    sickpay_masterlst = []
    master_lst = []

    # Dics
    embargo_dct = {}

    # Deep copy incap dict into embargo dict
    embargo_dct = copy.deepcopy(incap_dct)

    # Prepare list of merged incap periods
    # Flatten dictionary values
    incap_masterlst = flat(list(incap_dct.values()))
    # Remove empty nested lists
    incap_masterlst = purify(incap_masterlst)
    # Merge overlapping periods
    incap_masterlst = merge(incap_masterlst)

    # --- TRIAL PERIOD --- #

    # Check if user selected trial period evaluation
    if trial_relevance == True:

        # Gather weekday numbers from user input
        # Source: https://stackoverflow.com/a/70202124/14819955
        weekday_mapping = {day: index for index, day in enumerate((
        "Montag / Monday", "Dienstag / Tuesday", "Mittwoch / Wednesday", "Donnerstag / Thursday", "Freitag / Friday", "Samstag / Saturday", "Sonntag / Sunday"))}
        for weekday in workdays_input:
            workdays_num.append(weekday_mapping.get(weekday, weekday))


        # Extract probation period duration from user input
        if trial_input in ["No mention of probation period", "Keine Angaben zur Probezeit"]:
            trial_dur = 1
        else:
            trial_dur = int(trial_input)

        # Calculate probation period end date
        trial_lst.insert(1, min(trial_lst[0].shift(months=+trial_dur), termination_dt)) # BGer 4C.45/2004
        trial_lst[1] = subtract_corr(trial_lst[0], trial_lst[1])

        # Assume no trial extension
        trial_extension = False
        # Check if any incapacity date lies within probation period
        for incap_sublst in incap_masterlst:
            for day in arrow.Arrow.range("day", incap_sublst[0], incap_sublst[1]):
                if day.is_between(trial_lst[0], trial_lst[1], "[]"):
                    trial_extension = True
                    break

        if trial_extension == True:
            for incap_sublst in incap_masterlst:
                
                # Gather future holidays for 2 years
                for day in arrow.Arrow.range("days", trial_lst[0], limit=730):
                    if holiday_checker(day, workplace) == True:
                        holidays.append(day)
                                
                # Gather working days during probation period
                for day in arrow.Arrow.range("days", max(trial_lst[0], incap_sublst[0]), min(trial_lst[1], incap_sublst[1])):
                    # Add date to list if it is a working day, not a holiday and not already in the list
                    if (day.weekday() in workdays_num) and (day not in holidays) and (day not in missed_workdays):
                        missed_workdays.append(day)

                # Gather working days during probation period extension and match against amount of missed working days
                for day in arrow.Arrow.range("days", max(trial_lst[1], incap_sublst[1]).shift(days=+1), limit=365):
                    if (day.weekday() in workdays_num) and (day not in holidays) and (len(missed_workdays) > len(repeated_workdays)):
                        repeated_workdays.append(day)

                # Set extension end date
                trial_lst[1] = min(repeated_workdays[-1], termination_dt) # cap at termination
                    
        # Shift regular employment start date to after trial period
        reg_employment_lst[0] = trial_lst[-1].shift(days=+1)

        # Count probation period extension
        trial_extension_dur = len(missed_workdays)
    else:
        trial_extension_dur = 0


    # --- CASE: ILLNESS OR ACCIDENT --- #

    # Selected case type
    if incapacity_type == "illacc":

        # Loop through incapacities by incapacity
        for key, value in embargo_dct.items():

            # Keep score of embargo days for each incap
            embargo_cap_loop = 30 # start with lowest
            embargo_claimed_loop = 0
            embargo_unclaimed_loop = 0

            # Iterate over sublists
            for embargo_sublst in value:

                # Skip empty lists
                if embargo_sublst == []:
                    continue

                # Only check new lists, skip other lists
                if embargo_sublst in embargo_negative:
                    continue

                # Continue with next iteration if incapacitiy start date lies before the beginning of employment, empty sublist
                if reg_employment_lst[0] >= embargo_sublst[1]:
                    embargo_sublst.clear() # Clear list
                    continue

                # Set embargo cap according to seniority at beginning of incapacity
                if embargo_sublst[0] < syears[1]:
                    embargo_cap_loop = 30 # cap at 29 days incl. start and end date
                elif embargo_sublst[0] >= syears[5]:
                    embargo_cap_loop = 180 # cap at 180 days incl. start and end date
                else:
                    embargo_cap_loop = 90 # cap at 90 days incl. start and end date

                # Skip if embargo_cap has been exceeded
                if embargo_claimed_loop >= embargo_cap_loop:
                    embargo_sublst.clear()
                    continue

                # Count unclaimed days, max 1 since 1 day will be subtracted
                embargo_unclaimed_loop = max(1, (embargo_cap_loop - embargo_claimed_loop))

                # Set embargo start date
                embargo_sublst[0] = max(reg_employment_lst[0], embargo_sublst[0]) # starts on reg employment at the earliest

                # Check if service year 1, 5 is crossed during embargo period, adjust embargo cap
                if syears[1].is_between(embargo_sublst[0], embargo_sublst[1], "[)"):
                    crossed_syear = 1
                    embargo_cap_loop = 90 # cap at 90 days incl. start and end date
                elif syears[5].is_between(embargo_sublst[0], embargo_sublst[1], "[)"):
                    crossed_syear = 5
                    embargo_cap_loop = 180 # cap at 180 days incl. start and end date
                else:
                    # Set embargo end date into embargo dict, max date after cap is reached
                    embargo_sublst[1] = min(embargo_sublst[0].shift(days=(embargo_unclaimed_loop - 1)), embargo_sublst[1])
                    # Count used days
                    embargo_claimed_loop = period_duration(embargo_sublst[0], embargo_sublst[1])
                    # Skip syear cleanup
                    crossed_syear = 0

                # Split embargo period if seniority threshold is crossed during embargo period
                # Put split embargo periods into dict key 11, 12, 13...
                if crossed_syear != 0:
                
                    # Save original end date
                    save_date_embargo_split = embargo_sublst[1]
                    # Set end of first period, max one day before syear change
                    embargo_sublst[1] = min(embargo_sublst[0].shift(days=(embargo_unclaimed_loop - 1)), syears[crossed_syear].shift(days=-1))
                    # Calculate used balance
                    embargo_claimed_loop += period_duration(embargo_sublst[0], embargo_sublst[1])
                    # Count unclaimed days
                    embargo_unclaimed_loop = max(1, (embargo_cap_loop - embargo_claimed_loop))

                    # Insert new list
                    new_embargo_sublist = []
                    value.insert((value.index(embargo_sublst) + 1), new_embargo_sublist)
                    # Set start of second period at syear change
                    new_embargo_sublist.insert(0, syears[crossed_syear])
                    # Set end of second period
                    new_embargo_sublist.insert(1, min(new_embargo_sublist[0].shift(days=(embargo_unclaimed_loop - 1)), save_date_embargo_split))
                    # Add to negative list to test against
                    embargo_negative.append(new_embargo_sublist)
                    # Count used days
                    embargo_claimed_loop += period_duration(new_embargo_sublist[0], new_embargo_sublist[1])


    # --- CASE: MILITARY OR CIVIL SERVICE --- #

    # Selected case type
    if incapacity_type == "milservice":
        for key, value in embargo_dct.items():
            for embargo_sublst in value:

                # Check if milservice duration was over 11 days
                milservice_dur = period_duration(embargo_sublst[0], embargo_sublst[1])
                if milservice_dur > 11:
                    # Set embargo start to 4 weeks prior
                    embargo_sublst[0] = embargo_sublst[0].shift(weeks=-4, days=-1)
                    # Set embargo end to 4 weeks after
                    embargo_sublst[1] = embargo_sublst[1].shift(weeks=+4, days=+1)

                # Delete if embargo ended before regular employment
                if reg_employment_lst[0] >= embargo_sublst[1]:
                    embargo_sublst.clear() # Clear list
                    continue

                # Set embargo beginning at start of reg employment
                embargo_sublst[0] = max(reg_employment_lst[0], embargo_sublst[0])

                # Forward beginning to regular employment end date
                if reg_employment_lst[0] >= embargo_sublst[0]:
                    embargo_sublst[0] = reg_employment_lst[0]

                # Set sick pay (Erwerbsersatz) during milservice, calculate total
                sickpay_dct[1] = [[embargo_sublst[0], embargo_sublst[1]]]


    # --- CASE: PREGNANCY --- #

    # Selected case type
    if incapacity_type == "preg":
        for key, value in embargo_dct.items():
            for embargo_sublst in value:
                
                # Set sick pay (maternity pay) to 14 weeks after confinement
                sickpay_dct[1] = [[embargo_sublst[1], embargo_sublst[1].shift(weeks=14)]]
                
                # Extend embargo to 16 weeks after confinement
                embargo_sublst[1] = embargo_sublst[1].shift(weeks=16, days=-1)
                sick_pay_claimed_total = period_duration(embargo_sublst[0], embargo_sublst[1])

                # Delete if embargo ended before regular employment
                if reg_employment_lst[0] >= embargo_sublst[1]:
                    embargo_sublst.clear() # Clear list
                    continue

                # Set embargo beginning at start of reg employment
                embargo_sublst[0] = max(reg_employment_lst[0], embargo_sublst[0])

                # Forward beginning to regular employment end date
                if reg_employment_lst[0] >= embargo_sublst[0]:
                    embargo_sublst[0] = reg_employment_lst[0]


    # --- Cleanup --- #

    # Prepare list of merged embargo periods
    # Flatten dictionary values
    embargo_masterlst = flat(list(embargo_dct.values()))
    # Remove empty nested lists
    embargo_masterlst = purify(embargo_masterlst)
    # Merge overlapping periods
    embargo_masterlst = merge(embargo_masterlst)


    # --- TERMINATION AND NOTICE PERIOD --- #

    # Check if user selected termination evaluation
    if termination_occurence == True:

        # Legal minimum notice period according to seniority
        if notice_period_input in ["No mention of notice period", "Keine Angaben zur Kündigungsfrist"]:
            if termination_dt < syears[1]:
                notice_period = 1
            elif termination_dt >= syears[5]:
                notice_period = 3
            else:
                notice_period = 2
        else:
            notice_period = int(notice_period_input)

        # Calculate regular employment period end date
        reg_employment_lst[1] = push_endpoint(reg_employment_lst[1], endpoint)

        # Determine notice period start date (BGE 134 III 354)
        notice_period_lst.insert(0, reg_employment_lst[1].shift(days=1))

        # Determine notice period end date
        notice_period_lst.insert(1, reg_employment_lst[1].shift(months=+notice_period))

        # Push notice period end date if required
        notice_period_lst[1] = push_endpoint(notice_period_lst[1], endpoint)

        # Backwards check of notice period duration, truncate
        while notice_period_lst[0].shift(months=+notice_period) < notice_period_lst[1]:
            notice_period_lst[0] = notice_period_lst[0].shift(months=+1)
            reg_employment_lst[1] = notice_period_lst[0].shift(days=-1)

        # Calculate new employment end date
        new_employment_edt = notice_period_lst[-1]

        # Only calculate if incap has occured
        if incapacity_type != False:

            # Calculate total notice overlap, i.e. how many days of original notice period were missed
            notice_overlap = 0
            # Duration of original notice period
            for embargo_sublst in embargo_masterlst:
                notice_overlap += overlap_calc(notice_period_lst[0], embargo_sublst[0], notice_period_lst[1], embargo_sublst[1])


            # Shift missed notice period days, start and end date
            if notice_overlap != 0:

                notice_comp_lst.append(notice_period_lst[1].shift(days=+1))
                notice_comp_lst.append(notice_period_lst[1].shift(days=+notice_overlap))
                # Handle consecutive interruptions of notice period
                notice_comp_lst = grow(notice_comp_lst, embargo_masterlst) 

                # Create extension if needed
                if not endpoint in ["Termination date anytime", "Kündigungstermin jederzeit"]:
                    notice_ext_lst.insert(0, notice_comp_lst[1].shift(days=+1))
                    notice_ext_lst.insert(1, push_endpoint(notice_comp_lst[1], endpoint))
                    single_date(notice_ext_lst, 0, 1)
                    new_employment_edt = notice_ext_lst[1]
                else:
                    new_employment_edt = notice_comp_lst[1]
        
        # Set variables if no incaps were given
        else:
            notice_overlap = 0

    # Set termination date to regular employment endt date if no termination date was given
    else: 
        notice_overlap = 0
        new_employment_edt = termination_dt
        termination_dt = termination_dt.shift(years=200) # Shift out of sight


    # --- SICK PAY --- #

    if incapacity_type == "illacc":

        # Sick pay matrix, starting after first year of service
        # Source: https://www.gerichte-zh.ch/themen/arbeit/waehrend-arbeitsverhaeltnis/arbeitsverhinderung/krankheit-und-unfall.html
        # Include placeholder for index 0 since it is 3 weeks for all cantons
        pay_matrix = [
            ["", 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42], # ZH (weeks)
            ["", 1, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 6, 6 ,6, 6, 6 ,6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6], # BS / BL (months)
            ["", 1, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 6 ,6, 6, 6 ,6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6], # BE (months)
        ]

        # Choose sick pay duration
        if workplace in ["ZH", "SH", "TG"]:
            canton = 0
            unit = "weeks"
        elif workplace in ["BS", "BL"]:
            canton = 1
            unit = "months"
        else:
            canton = 2
            unit = "months"

        # Split sick pay periods into years
        for key, value in incap_dct.items():
            for incap_sublst in value:

                # Skip empty lists
                if incap_sublst == []:
                    continue

                # Skip sublists that end before beginning of claim
                if employment_sdt.shift(months=+3) >= incap_sublst[1]:
                    continue

                sickpay_sublst_1 = copy.deepcopy(incap_sublst)
                sickpay_sublst_2 = []
                
                # Define sick pay start date max 3 months into employment
                sickpay_sublst_1[0] = max(employment_sdt.shift(months=+3), sickpay_sublst_1[0])

                # Calculate seniority at the beginning of the incapacity
                # Source: https://stackoverflow.com/a/70038244/14819955
                sick_pay_syear_start_index = get_last_index(syears, lambda x: x < sickpay_sublst_1[0]) + 1 # +1 to denote year 0 as first syear

                # Calculate seniority at the end of the incapacity
                sick_pay_syear_end_index = get_last_index(syears, lambda x: x < sickpay_sublst_1[1]) + 1 # +1 to denote year 0 as first syear

                # Compare seniority at start and end, split if not the same
                # Group into dict according to start year
                if sick_pay_syear_start_index != sick_pay_syear_end_index: # not in the same year
                    # Hold original enddate
                    save_date_sick_pay_split = sickpay_sublst_1[1]
                    # Cap first period a day before syear
                    sickpay_sublst_1[1] = min(sickpay_sublst_1[1], syears[sick_pay_syear_start_index].shift(days=-1))
                    # Split period after syear
                    sickpay_sublst_2.insert(0, syears[sick_pay_syear_start_index])
                    sickpay_sublst_2.insert(1, save_date_sick_pay_split)
                    # Sort second period into dict according to syear
                    sickpay_dct[sick_pay_syear_end_index].append(sickpay_sublst_2)

                # Sort first period into dict according to syear
                sickpay_dct[sick_pay_syear_start_index].append(sickpay_sublst_1)

        # Keep score of total
        sick_pay_claimed_total = 0
        # Loop through incapacities according to syear
        for key, value in sickpay_dct.items():

            # Keep score of sick pay for each loop (year)
            sick_pay_cap = 21 # start with lowest lowest
            sick_pay_claimed_loop = 0
            sick_pay_unclaimed_loop = 0

            # Iterate over sublists
            for sickpay_sublst in value:

                # Skip empty lists
                if sickpay_sublst == []:
                    continue

                # Calculate sick pay according to service year
                if syears[key] == syears[1]:
                    sick_pay_cap = period_duration(sickpay_sublst[0], sickpay_sublst[0].shift(weeks=+3, days=-1))
                else:
                    # Add +1 to move query to the right index in sick pay matrix
                    sick_pay_cap = period_duration(sickpay_sublst[0], sickpay_sublst[0].shift(**{unit:(pay_matrix[canton][key - 1])}, days=-1))

                # Check if cap has been exceeded
                if sick_pay_claimed_loop >= sick_pay_cap:
                    sickpay_sublst.clear() # Clear list
                    continue

                # Calculate sick pay unclaimed
                sick_pay_unclaimed_loop = max(1, (sick_pay_cap - sick_pay_claimed_loop))

                # Set sick pay end date, cap sick pay at the earliest relevant occurence
                sickpay_sublst[1] = min(sickpay_sublst[0].shift(days=+sick_pay_unclaimed_loop - 1), sickpay_sublst[1], new_employment_edt)

                # Count used sick days
                sick_pay_claimed_loop += period_duration(sickpay_sublst[0], sickpay_sublst[1])

                # Count total
                sick_pay_claimed_total += sick_pay_claimed_loop

        # Delete empty syear keys from dict
        for key in list(sickpay_dct.keys()):
            if sickpay_dct[key] == []:
                del sickpay_dct[key]

    # Merge overlapping dictionary values for each year
    # Prepare list of merged embargo periods
    # Flatten dictionary values
    sickpay_masterlst = flat(list(sickpay_dct.values()))
    # Remove empty nested lists
    sickpay_masterlst = purify(sickpay_masterlst)
    # Merge overlapping periods
    sickpay_masterlst = merge(sickpay_masterlst)


    # --- EVALUATION AND CLEANUP --- #

    # Output
    valid_termination  = lang("✅ Termination is valid.", "✅ Kündigung ist gültig.")
    invalid_termination = lang("⛔ TERMINATION IS INVALID.", "⛔ KÜNDIGUNG UNGÜLTIG")
    no_termination = lang("[--> No termination evaluated]", "[--> Keine Kündigung evaluiert]")

    # Standard case
    # Termination during prbation period
    if termination_occurence == False:
        termination_case = "no_case"
    # Termination without issue
    if termination_occurence == True:
        termination_case = "standard_case"
    # Termination during trial
    if (termination_occurence == True) and termination_dt.is_between(trial_lst[0], trial_lst[-1], "[]"):
        termination_case = "trial_case"
    # Termination during embargo period
    if (termination_occurence == True) and (incapacity_type != False):
        for embargo_sublst in embargo_masterlst:
            if termination_dt.is_between(embargo_sublst[0], embargo_sublst[-1], "[]"):
                termination_case = "embargo_case"
                break


    # --- Termination case: No case --- #

    if termination_case == "no_case":
        termination_validity = no_termination
        reason = lang("[--> No termination evaluated]", "[--> Keine Kündigung ausgewertet]")
        new_employment_edt = lang("[--> No termination evaluated]", "[--> Keine Kündigung ausgewertet]")

    # --- Termination case: Standard case --- #

    if termination_case == "standard_case":
        termination_validity = valid_termination
        reason = lang("Regular termination of employment.", "Ordentliche Kündigung des Arbeitsverhältnisses.")

    # --- Termination case: TERMINATION DURING TRIAL PERIOD --- #

    # Adjust varibles
    if termination_case == "trial_case":
        termination_validity = valid_termination
        reason = lang("Termination during probation period.", "Kündigung während Probezeit.")

        # Set notice period according to user input
        if (trial_notice_input == "Not specified in contract") or (trial_notice_input == "Keine Angaben im Arbeitsvertrag"):
            trial_notice_period = 7
        else:
            trial_notice_period = int(trial_notice_input)

        # Set end of trial period to termination date
        trial_lst[1] = termination_dt
        # Adjust notice period
        notice_period_lst[0] = termination_dt.shift(days=+1)
        notice_period_lst[1] = termination_dt.shift(days=+trial_notice_period)
        notice_ext_lst.clear()
        notice_comp_lst.clear()
        notice_overlap = 0
        reg_employment_lst.clear()
        embargo_dct.clear()
        embargo_masterlst.clear()
        new_employment_edt = notice_period_lst[-1]


    # --- Termination case: TERMINATION DURING EMBARGO PERIOD --- #

    # Adjust varibles
    if termination_case == "embargo_case":
        termination_validity = invalid_termination
        reason = lang("The termination was issued during an embargo period.", "Die Kündigung wurde während einer Sperrfrist ausgesprochen.")
        notice_period_lst.clear()
        notice_overlap = 0
        reg_employment_lst[1] = reg_employment_lst[1].shift(years=+3) # showing that employment continues
        notice_comp_lst.clear()
        notice_ext_lst.clear()
        new_employment_edt = lang("[--> No valid termination]", "[--> Keine gültige Kündigung]")

    # --- Cleanup sick pay and embargo periods --- #
    # Delete sick pay and embargo periods after valid terminatio
    if (termination_case == "standard_case") or (termination_case == "trial_case"):
        for sickpay_sublst in sickpay_masterlst:

            # Delete sick pay that starts after end of employment
            if sickpay_sublst[0] > new_employment_edt:
                sickpay_sublst.clear() # Clear list
                continue

            # Cap sick pay that surpasses end of employment
            if new_employment_edt.is_between(sickpay_sublst[0], sickpay_sublst[1], "[]"):
                sickpay_sublst[1] = new_employment_edt
                continue

        for embargo_sublst in embargo_masterlst:

            # Delete embargo that starts after end of employment
            if embargo_sublst[0] > new_employment_edt:
                embargo_sublst.clear()
                continue

        sickpay_masterlst = purify(sickpay_masterlst)    
        embargo_masterlst = purify(embargo_masterlst)


    # --- OUTPUT SUMMARY --- #

    session.set_env(output_max_width = "1080px")

    # Remove progress bar
    output.remove("scope_progress")    
    output.clear("scope_input_instructions")

    # Summary of most important datapoints
    with output.use_scope("scope_res_general"):

        output.put_markdown(lang("""## Key Results""", """## Wichtigste Resultate""")).style('margin-top: 20px'),

        if termination_occurence != False:
            output.put_row([
                output.put_markdown(lang("""**Validity of Termination:**""", """**Gültigkeit Kündigung:**""")),
                output.put_markdown(termination_validity),
            ], size="35% auto auto")
            output.put_row([
                output.put_markdown(lang("""**Reason:**""", """**Begründung:**""")),
                output.put_markdown(reason),
            ], size="35% auto auto")

        if trial_relevance != False:
            output.put_row([
                output.put_markdown(lang("""**Missed Workdays Probation Period:**""", """**Verpasste Arbeitstage Probezeit:**""")),
                output.put_markdown(str(trial_extension_dur)),
            ], size="35% auto auto")
            output.put_row([
                output.put_markdown(lang("""**Probation Period End Date:**""", """**Enddatum Probezeit:**""")),
                output.put_markdown(trial_lst[-1].format("DD.MM.YYYY")),
            ], size="35% auto auto")

        if termination_occurence != False:
            output.put_row([
                output.put_markdown(lang("""**Compensation Days Notice Period:**""", """**Kompensationstage Kündigungsfrist:**""")),
                output.put_markdown(str(notice_overlap)),
            ], size="35% auto auto")
            output.put_row([
                output.put_markdown(lang("""**Employment End Date:**""", """**Enddatum Anstellung:**""")),
                output.put_markdown(new_employment_edt.format("DD.MM.YYYY")),
            ], size="35% auto auto")

        if (termination_occurence == False) and (trial_relevance == False):
            output.put_row([
                output.put_markdown(lang("""**[--> See below for detailed results.]**""", """**[--> Siehe detaillierte Auflistung unten.]**""")),
            ])

    # Start of detailed results

    # Scope for the summary of the trial period
    with output.use_scope("scope_res_trial"):

        output.put_markdown(lang("""## Detailed Results """, """## Detaillierte Ergebnisse""")).style('margin-top: 30px')
        output.put_markdown(lang("""### Probation Period""", """### Probezeit""")).style('margin-top: 20px')

        if trial_relevance == True:

            tbl_trial = Table()
            tbl_trial_headers = [
                lang("", ""),
                lang("Start", "Start"),
                lang("End", "Ende"),
                lang("Duration", "Dauer"),
            ]
            tbl_trial_rows = [[lang("Probation Period", "Probezeit"), trial_lst[0].format("DD.MM.YYYY"), trial_lst[1].format("DD.MM.YYYY"), str(period_duration(trial_lst[0], trial_lst[1])) + lang(" days", " Tage")]]

            tbl_trial.add(tbl_trial_headers, tbl_trial_rows)

            output.put_html(tbl_trial.render_notebook()).style('margin-top: 40px')
        
        else:
            output.put_markdown(lang("""**[--> No probation period evaluated]**""", """**[--> Keine Probezeit ausgewertet]**""")),

    # Scope for the summary of incapacities as declared by user input
    with output.use_scope("scope_res_incap"):

        output.put_markdown(lang("""### Incapacities (Your Input)""", """### Arbeitsunfähigkeiten (Dein Input)""")).style('margin-top: 20px')

        if incapacity_type != False:

            tbl_incap_headers = [
                lang("No.", "Nr."),
                lang("Start", "Start"),
                lang("End", "Ende"),
                lang("Duration", "Dauer"),
            ]

            tbl_incap = Table()
            tbl_incap_rows = []
            
            # List incapacities (dict is used for incap number)
            for key, value in incap_dct.items():
                for incap_sublst in value:
                    if incap_sublst != []:
                        tbl_lst = []
                        tbl_lst.append(str(key) + "." + str(value.index(incap_sublst)))
                        tbl_lst.append(incap_sublst[0].format("DD.MM.YYYY"))
                        tbl_lst.append(incap_sublst[1].format("DD.MM.YYYY"))
                        tbl_lst.append(str(period_duration(incap_sublst[0], incap_sublst[1])) + lang(" days", " Tage"))
                        tbl_incap_rows.append(tbl_lst)

            tbl_incap.add(tbl_incap_headers, tbl_incap_rows)

            output.put_html(tbl_incap.render_notebook()).style('margin-top: 40px')

        else:
            output.put_markdown(lang("""**[--> No incapacities evaluated]**""", """**[--> Keine Arbeitsunfähigkeiten ausgewertet]**""")),

    # Scope for the summary of any embargo periods
    with output.use_scope("scope_res_embargo_merged"):

        output.put_markdown(lang("""### Embargo Periods""", """### Sperrfristen""")).style('margin-top: 20px')

        if incapacity_type != False:

            tbl_embargo = Table()
            tbl_embargo_rows = []

            # Count
            i = 1
            for embargo_sublst in embargo_masterlst:
                tbl_lst = []
                tbl_lst.append(str(i))
                tbl_lst.append(embargo_sublst[0].format("DD.MM.YYYY"))
                tbl_lst.append(embargo_sublst[1].format("DD.MM.YYYY"))
                tbl_lst.append(str(period_duration(embargo_sublst[0], embargo_sublst[1])) + lang(" days", " Tage"))
                tbl_embargo_rows.append(tbl_lst)
                i += 1

            tbl_embargo.add(tbl_incap_headers, tbl_embargo_rows)

            output.put_html(tbl_embargo.render_notebook()).style('margin-top: 40px')

        else:
            output.put_markdown(lang("""**[--> No embargo periods evaluated]**""", """**[--> Keine Sperrfristen ausgewertet]**""")),

    # Scope for the summary of any sick pay periods
    with output.use_scope("scope_res_sp"):

        output.put_markdown(lang("""### Sick Pay Periods""", """### Perioden Lohnfortzahlung """)).style('margin-top: 20px'),

        if incapacity_type != False:

            tbl_sp = Table()
            tbl_sp_rows = []

            # Count iterations
            i = 1
            for sickpay_sublst in sickpay_masterlst:
                tbl_lst = []
                tbl_lst.append(str(i))
                tbl_lst.append(sickpay_sublst[0].format("DD.MM.YYYY"))
                tbl_lst.append(sickpay_sublst[1].format("DD.MM.YYYY"))
                tbl_lst.append(str(period_duration(sickpay_sublst[0], sickpay_sublst[1])) + lang(" days", " Tage"))
                tbl_sp_rows.append(tbl_lst)
                i += 1

            tbl_sp.add(tbl_incap_headers, tbl_sp_rows)

            output.put_html(tbl_sp.render_notebook()).style('margin-top: 40px')

        else:
            output.put_markdown(lang("""**[--> No sick pay periods evaluated]**""", """**[--> Keine Lohnfortzahlungsfristen ausgewertet]**""")),

    # Scope for the summary of notice period
    with output.use_scope("scope_res_notice"):

        output.put_markdown(lang("""### Notice Period""", """### Kündigungsfrist""")).style('margin-top: 20px'),
        
        # Omit if no notice period was evaluated
        if (termination_occurence == True) and (termination_case != "embargo_case"):

            tbl_np = Table()
            tbl_np_headers = [
                lang("Type", "Art"),
                lang("Start", "Start"),
                lang("End", "Ende"),
                lang("Duration", "Dauer"),
            ]

            tbl_np_rows = []

            tbl_np_rows.append([
                lang("Original Notice Period", "Ursprüngliche Kündigungsfrist"),
                notice_period_lst[0].format("DD.MM.YYYY"),
                notice_period_lst[1].format("DD.MM.YYYY"),
                str(period_duration(notice_period_lst[0], notice_period_lst[1])) + lang(" days", " Tage")
                ])

            try:
                tbl_np_rows.append([
                    lang("Notice Period Compensation", "Kompensation Kündigungsfrist"),
                    notice_comp_lst[0].format("DD.MM.YYYY"),
                    notice_comp_lst[1].format("DD.MM.YYYY"),
                    str(period_duration(notice_comp_lst[0], notice_comp_lst[1])) + lang(" days", " Tage")
                    ])
            except IndexError:
                tbl_np_rows.append([
                    lang("Notice Period Compensation", "Kompensation Kündigungsfrist"),
                    "X",
                    "X",
                    "X",
                    ])

            try:
                tbl_np_rows.append([
                    lang("Notice Period Extension", "Verlängerung Kündigungsfrist"),
                    notice_ext_lst[0].format("DD.MM.YYYY"),
                    notice_ext_lst[1].format("DD.MM.YYYY"),
                    str(period_duration(notice_ext_lst[0], notice_ext_lst[1])) + lang(" days", " Tage"),
                    ])
            except IndexError:
                tbl_np_rows.append([
                    lang("Notice Period Extension", "Verlängerung Kündigungsfrist"),
                    "X",
                    "X",
                    "X",
                    ])

            tbl_np.add(tbl_np_headers, tbl_np_rows)

            output.put_html(tbl_np.render_notebook()).style('margin-top: 40px')

        else:
            output.put_markdown(lang("""**[--> No notice period evaluated]**""", """**[--> Keine Kündigungsfrist ausgewertet]**""")),


    # --- OUTPUT VISUALIZATION - PREPARATION --- #

    # Convert dates from arrow to datetime for compatibility with Pandas
    # Strip time information
    # Convert standalone lists
    master_lst = [trial_lst, reg_employment_lst, notice_period_lst, notice_comp_lst, notice_ext_lst]
    for sublst in master_lst:
        for index, value in enumerate(sublst):
            if isinstance(value, arrow.Arrow):
                sublst[index] = value.datetime.date()

    # Copy local variables and covert to datetime
    local_vars = locals()
    output_dct = local_vars.copy()
    # Sort employment_sdt as global variable into dict
    output_dct["employment_sdt"] = employment_sdt
    # Convert
    for key, value in list(output_dct.items()):
        if isinstance(value, arrow.Arrow):
            output_dct[key] = value.datetime.date()


    # --- OUTPUT VISUALIZATION - GATHER DATA --- #

    # List of dataframes
    df_lst = []

    # Placeholder
    df_lst.append(pd.DataFrame(
        data=[[
            "[PH_T]",
            output_dct["termination_dt"],
            output_dct["termination_dt"],
            "stack_1"]],
        columns=["task", "start", "end", "stack"]))

    # Insert sick pay dict into dataframe
    for sickpay_sublst in sickpay_masterlst:
        if sickpay_sublst != []:
            df_lst.append(pd.DataFrame(
                data=[[
                    lang("Sick Pay", "Lohnfortzahlung"),
                    sickpay_sublst[0].datetime.date(),
                    sickpay_sublst[1].datetime.date(),
                    "stack_2"]],
                columns=["task", "start", "end", "stack"]))

    # Insert trial period into dataframe
    df_lst.append(pd.DataFrame(
        data=[[
        lang("Probation Period", "Probezeit"),
        check_index(trial_lst, 0),
        check_index(trial_lst, 1),
        "stack_3"]],
        columns=["task", "start", "end", "stack"]))

    # Insert regular employment into dataframe
    df_lst.append(pd.DataFrame(
        data=[[
        lang("Regular Employment","Reguläre Anstellung"),
        check_index(reg_employment_lst, 0),
        check_index(reg_employment_lst, 1),
        "stack_3"]],
        columns=["task", "start", "end", "stack"]))

    # Insert embargo period dict into dataframe
    if incapacity_type != False:
        for embargo_sublst in embargo_masterlst:
            df_lst.append(pd.DataFrame(
                data=[[
                lang("Embargo Period", "Sperrfrist"),
                embargo_sublst[0].datetime.date(),
                embargo_sublst[1].datetime.date(),
                "stack_3"]],
                columns=["task", "start", "end", "stack"]))

    # Insert regular notice period into dataframe
    df_lst.append(pd.DataFrame(
        data=[[
        lang("Regular Notice Period", "Ordentliche Kündigungsfrist"),
        check_index(notice_period_lst, 0),
        check_index(notice_period_lst, 1),
        "stack_3"]],
        columns=["task", "start", "end", "stack"]))

    # Insert missed notice period compensation into dataframe
    df_lst.append(pd.DataFrame(
        data=[[
            lang("Compensation Missed Notice Period", "Kompensation verpasste Kündigungsfrist"),
            check_index(notice_comp_lst, 0),
            check_index(notice_comp_lst, 1),
            "stack_3"]],
        columns=["task", "start", "end", "stack"]))

    # Insert notice period extension into dataframe
    df_lst.append(pd.DataFrame(
        data=[[
            lang("Notice Period Extension", "Verlängerung Kündigungsfrist"),
            check_index(notice_ext_lst, 0),
            check_index(notice_ext_lst, 1), "stack_3"]],
        columns=["task", "start", "end", "stack"]))

    # Insert incapacity dict into dataframe
    if incapacity_type != False:
        for incap_sublst in incap_masterlst:
            if incap_sublst != []:
                df_lst.append(pd.DataFrame(
                    data=[[
                        lang("Incapacity", "Arbeitsunfähigkeit"),
                        incap_sublst[0].datetime.date(),
                        incap_sublst[1].datetime.date(),
                        "stack_4"]],
                    columns=["task", "start", "end", "stack"]))

    # Insert place holders into dataframe
    df_lst.append(pd.DataFrame(
        data=[[
            "[PH_B]",
            output_dct["termination_dt"],
            output_dct["termination_dt"],
            "stack_5"]],
        columns=["task", "start", "end", "stack"]))

    # Combine dataframes
    df = pd.concat(df_lst, ignore_index=True, sort=False)

    # --- OUTPUT VISUALIZATION - FORMAT --- #

    fig = px.timeline(df,
                x_start="start",
                x_end="end",
                y="stack",
                opacity=1,
                color="task",
                color_discrete_map={
                    "[PH_T]": "#ffffff",
                    "Sick Pay": "#f032e6", "Lohnfortzahlung": "#f032e6",
                    "Probation Period": "#f58231", "Probezeit": "#f58231",
                    "Regular Employment": "#3cb44b", "Reguläre Anstellung": "#3cb44b",
                    "Notice Period": "#000075", "Kündigungsfrist": "#000075",
                    "Compensation Missed Notice Period": "#4363d8", "Kompensation verpasste Kündigungsfrist": "#4363d8",
                    "Sperrfrist": "#e6194B", "Embargo Period": "#e6194B",
                    "Notice Period Extension": "#911eb4", "Verlängerung Kündigungsfrist": "#911eb4",
                    "Incapacity": "#9A6324", "Arbeitsunfähigkeit": "#9A6324",
                    "[PH_B]": "#ffffff",
                },
                width=1000,
                height=700,
                hover_name="task",
                hover_data={"task":False,
                            "stack":False,
                            "start": True,
                            "end":True})

    config = {'displayModeBar': True,
              'displaylogo': False,
              'modeBarButtonsToRemove': ['select2d', 'lasso2d'],}

    fig.update_traces(marker_line_width=1.0, opacity=0.95)

    fig.update_xaxes(range=[reg_employment_lst[0], reg_employment_lst[1]])

    fig.update_layout(
        barmode="overlay",
        xaxis = dict(
            automargin=True,
            dtick="M12",
            tickformat="%d.%m.%Y",
            type="date",
            showgrid=True,
            rangeslider_visible=True),
        
        margin=dict(
            b=100,
            t=200,),

        yaxis = dict(
            automargin=True,
            visible=False,
            autorange="reversed",
            showgrid=True),
        
        legend=dict(
            title="",
            orientation="h",
            font_size=16,
            x=0,
            y=1.1),

        shapes = [
            dict(
            x0=termination_dt, x1=termination_dt, line_color="#DB162F", fillcolor="#DB162F", y0=0, y1=1, xref='x', yref='paper',
            line_width=3),
            dict(
            x0=syears[1], x1=syears[1], line_color="#3B6728", fillcolor="#3B6728", y0=0, y1=1, xref='x', yref='paper',
            line_width=1.5),
            dict(
            x0=syears[5], x1=syears[5], line_color="#3B6728", fillcolor="#3B6728", y0=0, y1=1, xref='x', yref='paper',
            line_width=1.5),
            ],
            
        
        annotations=[
            dict(
            x=termination_dt, y=1, xref='x', yref='paper',font=dict(size=16, color="#DB162F"),
            showarrow=False, xanchor='left', text=lang("Termination", "Kündigung")),
            dict(
            x=syears[1], y=0.05, xref='x', yref='paper',font=dict(size=16, color="#3B6728"),
            showarrow=False, xanchor='left', text="1Y"),
            dict(
            x=syears[5], y=0.05, xref='x', yref='paper',font=dict(size=16, color="#3B6728"),
            showarrow=False, xanchor='left', text="5Y"),
            ])


    # --- OUTPUT VISUALIZATION - MAKE OUTPUT --- #

    with output.use_scope("scope_visualization"):
        # Plotly output to PyWebIO
        plotly_html = fig.to_html(include_plotlyjs="require", full_html=False, config=config)
        output.put_markdown(lang("""
        ## Interactive Visualization

        IMPORTANT: The chart below is intended only as a visual aid.

        """, """
        ## Interaktive Visualisierung

        WICHTIG: Die nachfolgende Grafik ist nur als visuelle Hilfe gedacht.

        """)).style('margin-top: 20px'),
        output.put_collapse(lang("Further Information", "Ergänzende Hinweise",), [
            output.put_markdown(lang("""
            - An export of the chart area as PNG is possible via the control panel on the top right
            - Time periods of asingle day cannot be visualized

            ""","""
            - Ein Export als PNG ist über das Steuerpanel rechts oben möglich.
            - Die Visualisierung einzelner Tage ist nicht möglich

            """))]).style('margin-top: 20px'),
        output.put_html(plotly_html).style("border: 1px solid #dfe2e5")
