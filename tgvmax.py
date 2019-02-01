#!/usr/bin/env python2
import argparse
import logging

import requests

from bs4 import BeautifulSoup


TGVMAX_URL = "https://www.tgvmax.fr/api/"
HAPPYCARD_URL = "https://happycard.force.com/"

OAUTH2_URL = HAPPYCARD_URL + \
             "services/oauth2/authorize?response_type=code&client_id=%s" \
             "&redirect_uri=https://www.tgvmax.fr/sfauthcallback" \
             "&state=trainline%%7Cfr-FR%%7C%%7Creservation%%7Cinitrebon"

TOKEN_URL = TGVMAX_URL + "authenticate/token?authorization_code=%s"
FUTURE_URL = TGVMAX_URL + "account/%s/travels/future?vendorcode=VSC"
CONFIRM_URL = TGVMAX_URL + "account/%s/travels/confirm/%s/?vendorcode=VSC"


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
handler = logging.FileHandler('tgvmax.log')
handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s'))
logger.addHandler(handler)


def quick_extract(s, beg, end):
    ibeg = s.find(beg)
    iend = s.find(end, ibeg + len(beg))
    return s[ibeg + len(beg):iend]


def main(args):
    s = requests.Session()

    def handle_redirect(r):
        return s.get(quick_extract(r.text, "handleRedirect('", "');"))

    r = s.get(HAPPYCARD_URL + "SiteLogin")
    soup = BeautifulSoup(r.text, "html.parser")
    prefix = "com.salesforce.visualforce."
    state = soup.find(id=prefix + "ViewState")["value"]
    state_mac = soup.find(id=prefix + "ViewStateMAC")["value"]
    state_version = soup.find(id=prefix + "ViewStateVersion")["value"]

    elem = "loginPage:SiteTemplate:formulaire"
    r = handle_redirect(s.post(HAPPYCARD_URL + "SiteLogin", data={
        elem: "loginPage:SiteTemplate:formulaire",
        elem + ":j_id37": "Connexion",
        elem + ":login-field": args.username,
        elem + ":password-field": args.password,
        prefix + "ViewState": state,
        prefix + "ViewStateMAC": state_mac,
        prefix + "ViewStateVersion": state_version,
    }))

    r = handle_redirect(s.get(HAPPYCARD_URL + "apex/SiteHome"))
    beg = '"global.salesforce.authentication.client.id","value":"'
    client_id = quick_extract(r.text, beg, '"},')
    api_key = quick_extract(r.text, 'apikey":"', '"}}}')
    headers = {"X-Hpy-ApiKey": api_key}

    r = handle_redirect(s.get(OAUTH2_URL % client_id))
    code = quick_extract(r.text, '"search":"?code=', '&sfdc_community_id')

    r = s.get(TOKEN_URL % code, headers=headers)
    account_id = r.json()["accountId"]

    r = s.get(FUTURE_URL % account_id, headers=headers)
    count = r.json()["nbVoyageAConfirmer"]
    total = r.json()["totalVendor"]
    logger.info("%d/%d travels to confirm" % (count, total))

    travels = [travel for travel in r.json()["travels"]
               if travel["noShow"]["afficherBoutonConfirmer"]]
    for travel in travels:
        r = s.get(CONFIRM_URL % (account_id, travel["id"]), headers)

        confirmed = False
        for new_travel in r.json()["travels"]:
            if new_travel["id"] == travel["id"]:
                confirmed |= new_travel["noShow"]["voyageConfirme"]

        if confirmed:
            origin = travel["origin"]["label"]
            destination = travel["destination"]["label"]
            departure = travel["departureDateTime"]
            logger.info("Confirmed travel from %s to %s on %s"
                        % (origin, destination, departure))
        else:
            logger.warn("Failed to confirm travel")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--username', required=True)
    parser.add_argument('-p', '--password', required=True)
    main(parser.parse_args())
