#!/usr/bin/env python3

import irc.client as client
from peewee import peewee
import sys
try:
    from pyfiglet import Figlet
except:
    print("FOR FUCKS SAKE INSTALL PYFIGLET https://github.com/pwaller/pyfiglet")
    sys.exit(1)
import json
import base64
import time
import logging
import random
import copy
import operator
import _thread

# This is for debugging. It vomits on the screen all the irc stuff
logging.getLogger(None).setLevel(logging.DEBUG)
logging.basicConfig(format="%(asctime)s: %(name)s: %(levelname)"
                    "s (at %(filename)s:%(funcName)s:%(lineno)d): %(message)s")

class Donger(object):
    def __init__(self):
        # For future usage
        self.pending = {} # pending['Polsaker'] = 'ravioli'
        self.deathmatchpending = {}
        self.health = {} # health['ravioli'] = 69
        self.gamerunning = False
        self.deathmatch = False
        self.verbose = False
        self.turn = ""
        self.turnindex = 0
        self.allplayers = []
        self._turnleft = []
        self._paccept = {}
        self.aliveplayers = []
        self.deadplayers = []
        self.maxheal = {} # maxheal['Polsaker'] = -6
        self.roundstart = 0
        self.haspraised = []
        self.lastheardfrom = {}
        self.sourcehistory = []
        self.zombies = []
        self.lastpingreq = None
        self.accountsseenonthisgame = [] # hi,thisisanextremellylongvariablename
        
        self.extracommands = {} # Commands declarated by modules
        
        # thread for timeouts
        _thread.start_new_thread(self._timeouts, ())
        
        # Load the config..
        self.config = json.loads(open("config.json").read())
        
        # We will use this a lot, and I hate long variables
        self.primarychan = self.config['channel']
        self.auxchans = self.config['auxchans']
        self.statsurl = self.config['stats-url']

        # Create the irc object
        self.irc = client.IRCClient("donger")
        self.irc.configure(server = self.config['server'],
                           nick = self.config['nick'],
                           ident = self.config['nick'],
                           port = 6697,
                           gecos = "The supreme donger")
        # Create handlers and F U N stuff
        self.irc.addhandler("connect", self._connect) # for SASL
        self.irc.addhandler("authenticate", self._auth) # for SASL!!!1
        self.irc.addhandler("welcome", self._welcome) # For the autojoin
        self.irc.addhandler("pubmsg", self._pubmsg) # For commands
        self.irc.addhandler("privmsg", self._privmsg) # For private commands
        self.irc.addhandler("part", self._coward) # Coward extermination
        self.irc.addhandler("quit", self._coward) # ^
        self.irc.addhandler("join", self._join) # For custom messages on join
        self.irc.addhandler("account", self._account) # account-notify stuff
        self.irc.addhandler("ctcpreply", self._ctcpreply) # ctcp shit

        
        # Connect to the IRC
        self.irc.connect()

    def verboseoutput(self, stringtoprint): #This is going to replace the if self.verbose crap.
        if self.verbose:
            self.irc.privmsg(self.primarychan, stringtoprint)

    def _pubmsg(self, cli, ev):
        # Processing commands here
        
        if ev.splitd[0].startswith("!") or ev.arguments[0].startswith(cli.nickname) or ev.arguments[0].startswith("fuck off"):
            try:
                if ev.target != self.primarychan and ev.source == self.sourcehistory[-2] and ev.source == self.sourcehistory[-1] and time.time() - self.lastheardfrom[ev.source] < 10:
                    return #Si el usuario fue el último de los dos usuarios en hablar, y el último mensaje era antes de 10 segs, no hacer nada. Control de flood
            except IndexError:
                pass
            finally:
                self.lastheardfrom[ev.source] = time.time()
                self.sourcehistory.append(ev.source)
        else:
            return # If this works the way I think it will, it won't need to parse anything unless it starts with a ! or the cli.nickname.
        ev.splitd[0] = ev.splitd[0].lower() #Lower the commands.
        if ev.splitd[0] == "!fight" or ev.splitd[0] == "!deathmatch":
            if ev.target in self.auxchans:
                return
 
            if self.gamerunning:
                cli.privmsg(self.primarychan, "Hay una pelea en progreso.")
                return
                
            if len(ev.splitd) == 1 or ev.splitd[1] == "": # I hate you
                cli.privmsg(self.primarychan, "Puedes leer? Es {0} <nick> [othernick] ...".format(ev.splitd[0]))
                return
            
            if cli.channels[ev.target.lower()].users[ev.source.lower()].account is None:
                cli.privmsg(self.primarychan, "Debes estar identificado con NickServ para jugar!")
                return
            
            self.deathmatch = False
            self.verbose = False
            
            if "--verbose" in ev.splitd:
                ev.splitd.remove("--verbose")
                self.verbose = True
                cli.privmsg(self.primarychan, "Verbose mode activated (Will deactivate when a game ends)")

            if ev.splitd[0] == "!deathmatch":
                if cli.nickname in ev.splitd:
                    cli.privmsg(self.primarychan, "Disculpa, pero {0} no está disponible para un torneo a muerte.".format(cli.nickname))
                    return
                elif len(ev.splitd) != 2:
                    cli.privmsg(self.primarychan, "Los torneos a muerte son 1 contra 1.")
                    return
                self.deathmatch = True

            players = copy.copy(ev.splitd)
            del players[0]
            pplayers = []
            for i in players:
                try: # Check if the challenged user is on the channel..
                    cli.channels[self.primarychan].users[i.lower()]
                except:
                    cli.privmsg(self.primarychan, "No hay nadie llamado {0} en este canal".format(i))
                    return
                if cli.channels[self.primarychan].users[i.lower()].account is None:
                    cli.privmsg(self.primarychan, "\002{0}\002 no está identificado con nickserv!".format(i))
                    return
            
                if cli.channels[self.primarychan].users[i.lower()].host == ev.source2.host:
                    cli.privmsg(self.primarychan, "Deja de golpearte.")
                    return 
                
                pplayers.append(cli.channels[self.primarychan].users[i.lower()].nick)
            pplayers.append(ev.source)
            self.pending[ev.source.lower()] = pplayers
            if self.deathmatch == True:
                self.deathmatchpending[ev.source.lower()] = ev.splitd[1]
            else:
                try:
                    del self.deathmatchpending[ev.source.lower()]
                except:
                    pass

            self._paccept[ev.source2.nick.lower()] = copy.copy(pplayers)
            self._paccept[ev.source2.nick.lower()].remove(ev.source)
            if cli.nickname.lower() in players:
                cli.privmsg(self.primarychan, "TÚ PUEDES VERLO")
                self._paccept[ev.source2.nick.lower()].remove(cli.nickname)
                if self._paccept[ev.source2.nick.lower()] == []:
                    self.fight(cli, pplayers, ev.source2.nick.lower())
                    return
            if self.deathmatch == True:
                cli.privmsg(self.primarychan, "{1}: \002{0}\002 te ha retado a un torneo a muerte. El perdedor será baneado por 20 minutos. Para aceptar, use '!accept {0}'".format(ev.source, ", ".join(self._paccept[ev.source2.nick.lower()])))
            else:
                cli.privmsg(self.primarychan, "{1}: \002{0}\002 te ha retado. Para aceptar, use '!accept {0}'".format(ev.source, ", ".join(self._paccept[ev.source2.nick.lower()])))
        elif ev.splitd[0] == "!accept":
            self.deathmatch = False #We'll do this and check later if it's a deathmatch.

            if self.gamerunning:
                cli.privmsg(self.primarychan, "ESPERA HASTA QUE ESTE DESGRACIADO JUEGO TERMINE")
                return
                
            if len(ev.splitd) == 1 or ev.splitd[1] == "": # I hate you
                cli.privmsg(self.primarychan, "Puedes leer? Es !accept <nick>")
                return
            ev.splitd[1] = ev.splitd[1].lower()
            try:
                if ev.source not in self.pending[ev.splitd[1]]:
                    raise  # two in one
            except:
                cli.privmsg(self.primarychan, "Err... Quizás quisiste decir \002!fight {0}\002? Él nunca te ha retado.".format(ev.splitd[1]))
                return
            try: # Check if the challenged user is on the channel..
                cli.channels[self.primarychan].users[ev.splitd[1]]
            except:
                cli.privmsg(self.primarychan, "No hay nadie más - tal vez fueron intimidados por tu donger.")
                del self.pending[ev.splitd[1]]
                return
            
            self._paccept[ev.splitd[1].lower()].remove(ev.source)
            if self._paccept[ev.splitd[1].lower()] == []:
                try:
                    if self.deathmatchpending[ev.splitd[1].lower()] == ev.source:
                        self.deathmatch = True
                except KeyError:
                    self.deathmatch = False
                # Start the fight!!!
                self.fight(cli, self.pending[ev.splitd[1]], ev.splitd[1], self.deathmatch)
                del self.pending[ev.splitd[1]]
                del self._paccept[ev.splitd[1].lower()]
        elif ev.splitd[0] == "!hit":
            if not self.gamerunning:
                return
                
            if self.turn != ev.source.lower():
                cli.privmsg(self.primarychan, "Espera tu maldito turno o te mataré.")
                return
            
            if ev.source.lower() not in self.aliveplayers:
                cli.privmsg(self.primarychan, "LÁRGATE DE AQUÍ O TE MATARÉ! INTRUSO INTRUSO INTRUSO")
            
            if len(ev.splitd) != 1 and ev.splitd[1] != "":
                if ev.splitd[1].lower() not in self.aliveplayers and ev.splitd[1].lower() in list(self.health):
                    cli.privmsg(self.primarychan, "QUÉ?! REALMENTE QUIERES GOLPEAR A UN CADÁVER?!")
                    return
                elif ev.splitd[1].lower() not in self.aliveplayers:
                    cli.privmsg(self.primarychan, "QUÉ?! \002{0}\002 no está jugando!".format(ev.splitd[1]))
                    return
                nick = ev.splitd[1]
            else:
                allaliveplayers = copy.deepcopy(self.aliveplayers)
                allaliveplayers.remove(ev.source.lower())
                nick = random.choice(list(allaliveplayers))
                
            self.hit(ev.source.lower(), nick)
        elif ev.splitd[0] == "!heal":
            if not self.gamerunning:
                return
                
            if self.turn != ev.source.lower():
                cli.privmsg(self.primarychan, "Espera tu maldito turno o te mataré.")
                return
            
            if ev.source.lower() not in self.aliveplayers:
                cli.privmsg(self.primarychan, "LÁRGATE DE AQUÍ O TE MATARÉ! INTRUSO INTRUSO INTRUSO")
                return
            
            if ev.source.lower() in self.zombies:
                cli.privmsg(self.primarychan, "Los zombies no pueden sanar")
                return
            
            self.heal(ev.source)
        elif ev.splitd[0] == "!praise":
            if not self.gamerunning:
                return
                
            if self.turn != ev.source.lower():
                cli.privmsg(self.primarychan, "Espera tu maldito turno o te mataré.")
                return
            
            if ev.source.lower() not in self.aliveplayers:
                cli.privmsg(self.primarychan, "LÁRGATE DE AQUÍ O TE MATARÉ! INTRUSO INTRUSO INTRUSO")
                return

            if ev.source.lower() in self.haspraised or ev.source.lower() in self.zombies:
                cli.privmsg(self.primarychan, "Tus oraciones me aburren.")
                return
                
            if self.deathmatch:
                cli.privmsg(self.primarychan, "\"A dong's life is the most precious thing in the universe.\" You can't praise in deathmatches.")
                return
            
            if len(ev.splitd) != 1 and ev.splitd[1] != "":
                nick = ev.splitd[1]
                if ev.splitd[1].lower() not in self.aliveplayers and ev.splitd[1].lower() in list(self.health):
                    cli.privmsg(self.primarychan, "QUÉ?! REALMENTE QUIERES GOLPEAR A UN CADÁVER?!")
                    return
                if ev.splitd[1].lower() not in self.aliveplayers:
                    cli.privmsg(self.primarychan, "QUÉ?! \002{0}\002 no está jugando!".format(ev.splitd[1]))
                    return
            else:
                nick = ev.source.lower()

            praiseroll=random.randint(1, 3)
            self.countstat(ev.source.lower(), "praise")
            self.haspraised.append(ev.source.lower())
            if nick.lower() == cli.nickname.lower():
                praiseroll = 2
                cli.privmsg(self.primarychan, "Tú intentas mamar mi donger mientras luchas contra mí?")
                nick = ev.source
            if praiseroll == 1: #Heal
                self.heal(nick, "praise")
            elif praiseroll == 2: #Hit
                self.hit(cli.nickname.lower(), nick, "praise")
            elif praiseroll == 3:
                self.ascii("NOPE NOPE NOPE")
                self.getturn()
        elif ev.splitd[0] == "!cancel":
            try:
                self.pending[ev.source.lower()]
            except:
                cli.privmsg(self.primarychan, "Tú solo puedes usar !cancel si has hecho !fight")
                return
            if self.gamerunning:
                cli.privmsg(self.primarychan, "LA LUCHA HA COMENZADO, SI ERES UN COBARDE USA !QUIT")
                return
            self.deathmatchpending = {}
            self.deathmatch = False
            del self.pending[ev.source.lower()]
            del self._paccept[ev.source.lower()]
            self.deathmatchpending = {}
            self.deathmatch = False
            cli.privmsg(self.primarychan, "pelea de {0} cancelada".format(ev.source))
        elif ev.splitd[0] == "!reject":
            if self.gamerunning:
                return
            if len(ev.splitd) == 1 or ev.splitd[1] == "": # I hate you
                cli.privmsg(self.primarychan, "Puedes leer? Es !reject <nick>")
                return
            try:
                if ev.source not in self.pending[ev.splitd[1].lower()]:
                    raise  # two in one
            except:
                cli.privmsg(self.primarychan, "Pero... {0} nunca te retó!".format(ev.splitd[1]))
                return
            
            self.pending[ev.splitd[1].lower()].remove(ev.source)
            if len(self.pending[ev.splitd[1].lower()]) == 2 and cli.nickname in self.pending[ev.splitd[1].lower()]:
                self.pending[ev.splitd[1].lower()].remove(cli.nickname)
            self._paccept[ev.splitd[1].lower()].remove(ev.source)
            cli.privmsg(self.primarychan, "{0} ha huído del combate".format(ev.source))
            if len(self.pending[ev.splitd[1].lower()]) == 1:
                del self.pending[ev.splitd[1].lower()]
                del self._paccept[ev.splitd[1].lower()]
                cli.privmsg(self.primarychan, "Pelea cancelada")
                return
            
            if self._paccept[ev.splitd[1].lower()] == []:
                # Start the fight!!!
                self.fight(cli, self.pending[ev.splitd[1].lower()], ev.splitd[1].lower())
                del self.pending[ev.splitd[1]]
                del self._paccept[ev.splitd[1].lower()]
        elif ev.arguments[0].startswith(cli.nickname):
            if len(ev.splitd) > 1 and ev.splitd[1].lower().startswith("you"):
                cli.privmsg(ev.target, "No, {0}".format(ev.source)+ ev.arguments[0].replace(cli.nickname, ""))
            else:
                cli.privmsg(ev.target, ev.arguments[0].replace(cli.nickname, ev.source))
        elif ev.arguments[0].lower().startswith("fuck off " + cli.nickname):
            cli.privmsg(ev.target, "\001ACTION jode a {0}\001".format(ev.source))
        elif ev.splitd[0] == "!help":
            self.commandHelp(cli, ev)
        elif ev.splitd[0] == "!excuse":
            cli.privmsg(ev.target, self.randomLine("excuse"))
        elif ev.splitd[0] == "!jaden":
            cli.privmsg(ev.target, self.randomLine("jaden"))
        elif ev.splitd[0] == "!raise":
            cli.privmsg(ev.target, "ヽ༼ຈل͜ຈ༽ﾉ RAISE YOUR DONGERS ヽ༼ຈل͜ຈ༽ﾉ")
        elif ev.splitd[0] == "!ping":
            current_milli_time = int(round(time.time() * 1000))
            self.lastpingreq = ev.target
            cli.privmsg(ev.source, "\001PING {0}\001".format(current_milli_time))
        elif ev.splitd[0] == "!lower":
            cli.privmsg(ev.target, "┌༼ຈل͜ຈ༽┐ ʟᴏᴡᴇʀ ʏᴏᴜʀ ᴅᴏɴɢᴇʀs ┌༼ຈل͜ຈ༽┐")
        elif ev.splitd[0] == "!dong":
            cli.privmsg(ev.target, self.randomLine("donger"))
        elif ev.splitd[0] == "!ascii":
            if ev.target in self.auxchans:
                return
            if self.gamerunning:
                return
            if len(ev.splitd) > 1 and len(' '.join(ev.splitd[1:])) < 16:
                cli.privmsg(ev.target, Figlet("smslant").renderText(' '.join(ev.splitd[1:])))
            elif len(ev.splitd) > 1:
                cli.privmsg(ev.target, "Text must be 15 characters or less (that was {0} characters). Syntax: !ascii Fuck You".format(len(' '.join(ev.splitd[1:]))))
        elif ev.splitd[0] == "!health":
            if not self.gamerunning:
                return
            if len(ev.splitd[0]) > 1 or ev.splitd[1] == "":
                ev.splitd[1] = ev.source
            cli.privmsg(ev.target, "\002{0}\002's has \002{1}\002HP".format(ev.splitd[1], self.health[ev.splitd[1].lower()]))
        elif ev.splitd[0] == "!quit":
            if not self.gamerunning:
                #cli.privmsg(ev.target, "THE FUCKING GAME IS NOT RUNNING")
                return
            cli.devoice(ev.target, ev.source)
            self._coward(cli, ev)
        elif ev.splitd[0] == "!top" and ev.target == self.primarychan:
            players = Statsv2.select()
            # K, now we have to make our own arranging of stuff, damnit
            p = {}
            for player in players:
                if (player.fights + player.accepts) < 10:
                    continue # not counting players with less than 10 fights
                
                p[player.nick] = (player.wins - player.losses)
            
            p = sorted(p.items(), key=operator.itemgetter(1))
                
            c = 1
            for player in p[::-1]:
                cli.privmsg(ev.target, "{0} - \002{1}\002 (+\002{2}\002)".format(c, player[0].upper(), player[1]))
                c += 1
                if c == 4:
                    break
            if self.statsurl != "":
                cli.privmsg(ev.target, "Más estadísticas están disponibles en {0}".format(self.statsurl))
        elif ev.splitd[0] == "!mystats" or ev.splitd[0] == "!stats":
            if len(ev.splitd) != 1:
                nick = ev.splitd[1]
            else:
                nick = ev.source
            try:
                if cli.channels[ev.target.lower()].users[nick.lower()].account != None:
                    nick = cli.channels[ev.target.lower()].users[nick.lower()].account
            except:
                pass  # >_>
                
            try:
                player = Statsv2.get(Statsv2.nick == nick.lower())
                totaljoins = (player.wins + player.losses + player.quits + player.easywins) - (player.fights + player.accepts)
                cli.privmsg(ev.target, "\002{0}\002's stats: \002{1}\002 wins, \002{4}\002 easy wins, \002{2}\002 losses, \002{3}\002 coward quits, \002{5}\002 idle-outs, \002{6}\002 !praises, \002{7}\002 fights started, accepted \002{8}\002 fights, !joined \002{15}\002 fights (\002{9}\002 total fights), \002{10}\002 !hits, \002{11}\002 !heals, \002{12}\002HP of damage dealt and \002{13}\002 damage received. {14}".format(
                                        player.realnick, player.wins, player.losses, player.quits, player.easywins, player.idleouts, player.praises, player.fights, player.accepts, (player.wins + player.losses + player.quits), player.hits, player.heals, player.dcaused, player.dreceived, self.statsurl, totaljoins))
            except:
                cli.privmsg(ev.target, "No hay estadísticas registradas para \002{0}\002".format(nick))
        else:
            try:
                self.extracommands[ev.splitd[0]]
            except:
                return
            self.extracommands[ev.splitd[0]](self, cli, ev)
    
    def commandHelp(self, cli, ev):
        cli.privmsg(ev.target, "Te he enviado por mensaje privado mis comandos")
        cli.privmsg(ev.source, "Comandos disponibles solo por {0}:".format(self.primarychan))
        cli.privmsg(ev.source, "  !fight <nickname> [othernicknames]: Challenge another player")
        cli.privmsg(ev.source, "  !deathmatch <nickname>: Same as fight, but only 1v1, and loser is bant for 20 minutes.")
        cli.privmsg(ev.source, "  !ascii <text>: Turns any text 13 characters or less into ascii art")
        cli.privmsg(ev.source, "  !cancel: Cancels a !fight")
        cli.privmsg(ev.source, "  !reject <nick>: Cowardly rejects a !fight")
        cli.privmsg(ev.source, "Comandos disponibles siempre:")
        cli.privmsg(ev.source, "  !raise: Commands users to raise their dongers")
        cli.privmsg(ev.source, "  !excuse: Outputs random BOFH excuse")
        cli.privmsg(ev.source, "  !jaden: Outputs random Jaden Smith tweet")
        cli.privmsg(ev.source, "  !stats [player]: Outputs player's game stats (or your own stats)")
        cli.privmsg(ev.source, "  !top: Shows the three players with most wins")
    
    def _privmsg(self, cli, ev):
        if ev.splitd[0] == "!join":
            self.join(cli, ev.source, ev)

    def join(self, cli, fighter, ev):
        
        if not self.gamerunning:
            cli.privmsg(fighter, "EL MALDITO JUEGO NO HA INICIADO")
            return
            
        try:
            ev.splitd[1]
        except:
            ev.splitd.append("")
            
        try:
            fighter = fighter if ev.splitd[1] != "141592" else cli.nickname
            if fighter != cli.nickname:
                raise
        except:
            if cli.channels[self.primarychan.lower()].users[fighter.lower()].account in self.accountsseenonthisgame and fighter != cli.nickname and ev.splitd[1] != "zombie":
                cli.privmsg(fighter, "Deja de hacer trampa, qué estupidez. Para entrar como zombie usa !join zombie")
                return 
        if fighter.lower() in self.aliveplayers:
            cli.privmsg(fighter, "Tú estás jugando, estúpido.")
            return
        if fighter.lower() in self.deadplayers and ev.splitd[1] != "zombie":
            cli.privmsg(fighter, "No puedes volver a entrar una vez que estás muerto.")
            return
        if fighter.lower() in self.zombies:
            return
        elif ev.splitd[1] == "zombie":
            self.zombies.append(fighter.lower())
            if random.randint(1, 5) > 2:
                cli.privmsg(fighter, "No tienes cerebro y tu zombie murió")
                return
        
        if self.deathmatch == True:
            cli.privmsg(fighter, "No puedes entrar a un torneo a muerte")
            return
        self.playershealth = []
        for p in self.aliveplayers:
            self.playershealth.append(self.health[p])

        #Set joining player's health to the average health of current players
        self.health[fighter.lower()] = int(sum(self.playershealth, 0.0) / len(self.playershealth))
        self.maxheal[fighter.lower()] = 44
        if ev.splitd[1] == "zombie": # ooo zombie
            self.health[fighter.lower()] = int(self.health[fighter.lower()] / 1.3)
            cli.privmsg(self.primarychan, "\002{0}\002's ZOMBIE ENTRA A LA PELEA (\002{1}\002HP)".format(fighter.upper(), self.health[fighter.lower()]))
        else:
            cli.privmsg(self.primarychan, "\002{0}\002 ENTRA A LA PELEA (\002{1}\002HP)".format(fighter.upper(), self.health[fighter.lower()]))
        
        if fighter.lower() not in self.allplayers:
            self.allplayers.append(fighter.lower())

        self.accountsseenonthisgame.append(cli.channels[self.primarychan.lower()].users[fighter.lower()].account)
        self.aliveplayers.append(fighter.lower())
        cli.voice(self.primarychan, fighter)


    def hit(self, hfrom, to, modifier=None):
        if modifier == None and self.turn.lower() != hfrom.lower():
            return
        self.maxheal[hfrom.lower()] = 44

        damage = random.randint(18, 35)
        criticalroll = random.randint(1, 12) if hfrom.lower() not in self.zombies else 12

        if modifier == "praise":
            self.verboseoutput("Verbose: Praise. Forcing critical")
            criticalroll = 1
        else:
            self.countstat(hfrom, "hit")

        instaroll = random.randint(1, 50) if not self.deathmatch and hfrom.lower not in self.zombies else 50

        self.verboseoutput("Verbose: instaroll is {0}/50 (1 for instakill)".format(instaroll))
        self.verboseoutput("Verbose: criticalroll is {0}/12 (1 for critical)".format(criticalroll))
        self.verboseoutput("Verbose: Regular damage is {0}/35".format(damage))

        if instaroll == 1:
            self.verboseoutput("Verbose: Instakill. Removing player.".format(instaroll))
            self.ascii("instakill")

            self.death(hfrom, to)
            self.health[to.lower()] = -1

            if to.lower() != self.irc.nickname:
                self.irc.kick(self.primarychan, to, "REKT")
            else:
                self.irc.devoice(self.primarychan, self.irc.nickname)
            self.getturn()
            self.countstat(self.irc.channels[self.primarychan].users[to.lower()].nick, "loss")
            return
        elif criticalroll == 1:
            self.verboseoutput("Verbose: Critical hit, duplicating damage: {0}/70".format(damage*2))
            if modifier == "praise":
                self.ascii("FUCK YOU")
            else:
                self.ascii("critical")
            damage = damage * 2
        
        self.countstat(hfrom, "dmg", damage)
        self.countstat(to, "gotdmg", damage)
        self.health[to.lower()] -= damage
        if hfrom.lower() == self.irc.nickname.lower() and hfrom.lower() not in self.health:
            fromhp = "999999999"
        else:
            fromhp = self.health[hfrom.lower()]
        self.irc.privmsg(self.primarychan, "\002{0}\002 (\002{1}\002HP) deals \002{2}\002 to \002{3}\002 (\002{4}\002HP)".format(hfrom,
                                    str(fromhp), str(damage), self.irc.channels[self.primarychan].users[to.lower()].nick, str(self.health[to.lower()])))

        if self.health[to.lower()] <= 0:
            self.death(hfrom, to)
            if to.lower() != self.irc.nickname.lower():
                if self.deathmatch == True:
                    self.verboseoutput("Verbose: Deathmatch lost. Adding akick.".format(instaroll))
                    self.irc.privmsg("CHANSERV", "AKICK {0} ADD {1} !T 20 FUCKIN REKT - Lost deathmatch".format(self.primarychan, self.irc.channels[self.primarychan].users[to.lower()].account))
                self.irc.kick(self.primarychan, to, "REKT")
        self.getturn()
    
    def death(self, slayer, player):
        self.verboseoutput("Verbose: Death. Slayer: {0}, player: {1}".format(slayer, player))
        self.irc.devoice(self.primarychan, player)
        self.ascii("rekt")
        self.irc.privmsg(self.primarychan, "\002{0}\002 REKT {1}!".format(self.irc.channels[self.primarychan].users[slayer.lower()].nick, self.irc.channels[self.primarychan].users[player.lower()].nick))
        self.verboseoutput("Verbose: Removing dead player.")
        self.aliveplayers.remove(player.lower())
        self.deadplayers.append(player.lower())
        try:
            self._turnleft.remove(player.lower())
        except:
            pass
        self.countstat(self.irc.channels[self.primarychan].users[player.lower()].nick, "loss")

    
    def heal(self, nick, modifier=None):
        if modifier == None and self.turn.lower() != nick.lower():
            return
        if self.maxheal[nick.lower()] <= 23 and modifier != "praise":
            self.irc.privmsg(self.primarychan, "Sorry, bro. We don't have enough chopsticks to heal you.")
            return
        healing = random.randint(22, self.maxheal[nick.lower()] if modifier != "praise" else 40)
        if modifier == "praise":
            healing = healing * 2
            self.verboseoutput("Verbose: Praise. Forcing critical heal.")
            self.ascii("como sea")
        else:
            self.countstat(nick, "heal")
        
        self.health[nick.lower()] += healing
        self.verboseoutput("Verbose: Regular healing is {0}/{1}(/44)".format(healing, self.maxheal[nick.lower()]))
        self.maxheal[nick.lower()] = self.maxheal[nick.lower()] - 5

        if self.health[nick.lower()] > 100:
            self.health[nick.lower()] = 100
            self.irc.privmsg(self.primarychan, "\002{0}\002 heals for \002{1}HP\002, bringing them to \002100HP\002".format(nick, healing))
        else:
            self.irc.privmsg(self.primarychan, "\002{0}\002 heals for \002{1}HP\002, bringing them to \002{2}HP\002".format(nick, healing, self.health[nick.lower()]))
        self.getturn()

    
    # Here we handle ragequits
    def _coward(self, cli, ev):
        if self.gamerunning:
            if ev.source2.nick.lower() in self.aliveplayers:
                self.ascii("coward")
                self.irc.privmsg(self.primarychan, "El cobarde está muerto!")
                self.aliveplayers.remove(ev.source2.nick.lower())
                self.deadplayers.append(ev.source2.nick.lower())
                self.health[ev.source2.nick.lower()] = -1
                try:
                    self._turnleft.remove(ev.source2.nick.lower())
                except:
                    pass
                    
                if len(self.aliveplayers) == 1:
                    self.win(self.aliveplayers[0], stats=False)
                elif self.turn == ev.source2.nick.lower():
                    self.getturn()
                
                self.countstat(ev.source2.nick, "quit")
    
    # Adds something on the stats
    # ctype = win/loss/quit
    def countstat(self, nick, ctype, amt=0):
        try:
            nick = self.irc.channels[self.primarychan.lower()].users[nick.lower()].account
        except:
            return
        try:
            stat = Statsv2.get(Statsv2.nick == nick.lower())
        except:
            stat = Statsv2.create(nick=nick.lower(), losses=0, quits=0, wins=0, idleouts=0, accepts=0,
            dcaused=0, dreceived=0, easywins=0, fights=0, praises=0, realnick=nick, heals=0, hits=0)
        if ctype == "win":
            stat.wins += 1
        elif ctype == "loss":
            stat.losses += 1
        elif ctype == "quit":
            stat.quits += 1
        elif ctype == "idleout":
            stat.idleouts += 1
        elif ctype == "fight":
            stat.fights += 1
        elif ctype == "gotdmg":
            stat.dreceived += amt
        elif ctype == "dmg":
            stat.dcaused += amt
        elif ctype == "easywin":
            stat.easywins += 1
        elif ctype == "accept":
            stat.accepts += 1
        elif ctype == "praise":
            stat.praises += 1
        elif ctype == "heal":
            stat.heals += 1
        elif ctype == "hit":
            stat.hits += 1
            
        stat.save()
    
    def fight(self, cli, fighters, starter, deathmatch = False):
        self.prerules()
        self.countstat(starter, "fight")
        cli.mode(self.primarychan, "+m")
        if deathmatch == True:
            self.ascii("DEATHMATCH")
        if len(fighters) == 2:
            self.ascii(" V. ".join(fighters).upper(), "straight")
        else:
            cli.privmsg(self.primarychan, " V. ".join(fighters).upper())
        cli.privmsg(self.primarychan, "REGLAS:")
        cli.privmsg(self.primarychan, "1. Espera tu turno, una persona a la vez.")
        cli.privmsg(self.primarychan, "2. No seas tonto.")
        cli.privmsg(self.primarychan, " ")
        cli.privmsg(self.primarychan, "Usa !hit [nick] para atacar.")
        cli.privmsg(self.primarychan, "Usa !heal para sanar tus heridas.")
        cli.privmsg(self.primarychan, "Usa !praise [nick] para orar a los dioses (una vez por juego).")
        cli.privmsg(self.primarychan, "Usa '/msg {0} !join para ingresar a una pelea' .".format(cli.nickname))
        cli.privmsg(self.primarychan, " ")
        
        for i in fighters:
            if cli.channels[self.primarychan.lower()].users[i.lower()].account in self.accountsseenonthisgame:
                cli.privmsg(self.primarychan, "..... ESPERA QUÉ?! Alguien intenta entrar al juego con dos clones")
                cli.mode(self.primarychan, "-m")
                self.allplayers = []
                return
            self.accountsseenonthisgame.append(cli.channels[self.primarychan.lower()].users[i.lower()].account)

            self.maxheal[i.lower()] = 44
            self.health[i.lower()] = 100
            self.allplayers.append(i.lower())
            self.aliveplayers.append(i.lower())
            if i.lower() != starter.lower():
                self.countstat(i.lower(), "accept")
        self.prefight()
        self.ascii("FIGHT")
        cli.privmsg(self.primarychan, " ")
        random.shuffle(self.allplayers) # randomize turns
        
        self.fightstart()

        cli.voice(self.primarychan, fighters)
        self.haspraised = []
        self.deadplayers = []
        self.gamerunning = True
        self.getturn()
        
    def getturn(self):
        self.verboseoutput("Verbose: Getting turns")
        
        if self.turnindex > (len(self.allplayers) - 1):
            self.verboseoutput("Verbose: turnindex is greater than allplayers length minus 1 (first instance). Resetting turnindex to 0.")
            self.turnindex = 0
        
        while self.allplayers[self.turnindex] not in self.aliveplayers:
            self.verboseoutput("Verbose: Advancing turnindex by 1")
            self.turnindex += 1
            if self.turnindex > (len(self.allplayers) - 1):
                self.verboseoutput("Verbose: turnindex is greater than allplayers length minus 1 (second instance). Resetting turnindex to 0.")
                self.turnindex = 0
        
        if len(self.aliveplayers) == 1:
            self.verboseoutput("Verbose: Only one player left, ending the game")
            self.allplayers = []  # adding this twice! WOO!
            self.win(self.aliveplayers[0])
            return
                        
        self.turn = self.allplayers[self.turnindex]
        self.turnindex += 1
        self.roundstart = time.time()
        self.irc.privmsg(self.primarychan, "It is \002{0}\002's turn".format(self.irc.channels[self.primarychan].users[self.turn].nick))
        
        # AI
        if self.turn.lower() == self.irc.nickname.lower():
            time.sleep(random.randint(2, 4))
            self.processAI()
            
    def processAI(self):
        playerstohit = copy.copy(self.aliveplayers)
        playerstohit.remove(self.irc.nickname.lower())
        tohit = random.choice(playerstohit)
        requiredbothp = 40
        requiredtohithp = 29
        if self.health[self.irc.nickname.lower()] < requiredbothp and self.health[tohit] > requiredtohithp:
            self.verboseoutput("Verbose: AI: Less than {0} HP, opponent more than {1}. Healing.".format(requiredbothp, requiredtohithp))
            if self.maxheal[self.irc.nickname.lower()] <= 20:
                self.verboseoutput("Verbose: AI: Not enough chopsticks. Hitting.")
                self.irc.privmsg(self.primarychan, "!hit " + tohit) 
                self.hit(self.irc.nickname.lower(), tohit)
            else:
                self.irc.privmsg(self.primarychan, "!heal") 
                self.heal(self.irc.nickname.lower())
        else:
            self.verboseoutput("Verbose: AI: More than {0} HP or opponent less than {1}. Attacking.".format(requiredbothp, requiredtohithp))
            self.irc.privmsg(self.primarychan, "!hit " + tohit) 
            self.hit(self.irc.nickname.lower(), tohit)
    
    def win(self, winner, stats=True):
        self.verbose = False
        self.irc.mode(self.primarychan, "-m")
        self.irc.devoice(self.primarychan, winner)
        if len(list(self.health)) > 2:
            self.irc.privmsg(self.primarychan, "{0} REKT {1}!".format(self.irc.channels[self.primarychan].users[winner.lower()].nick, self._dusers(winner)))
        self.reset()
        if stats is True:
            self.countstat(self.irc.channels[self.primarychan].users[winner.lower()].nick, "win")
        else:
            self.countstat(self.irc.channels[self.primarychan].users[winner.lower()].nick, "easywin")

    def reset(self):
        self.aliveplayers = []
        self.deadplayers = []
        self.allplayers = []
        self.zombies = []
        self.health = {}
        self.accountsseenonthisgame = []
        self._turnleft = []
        self.gamerunning = False
        self.deathmatch = False
        self.deathmatchpending = {}
        self.turn = 0
        self.turnindex = 0
        self.roundstart = 0
        self.verbose = False
        self.nojoin = False
    
    def ascii(self, key, font="smslant"): #Only used in fights
        if "not gay".lower() in key.lower():
            key = key.upper()
            key = key.replace('NOT', '')
        self.irc.privmsg(self.primarychan, "\n".join([name for name in Figlet(font).renderText(key.upper()).split("\n")[:-1] if name.strip()]))

    # god, this is so shitty
    def randomLine(self, type):
        if type == "excuse":
            file = "stuff/excuse_list.txt"
        elif type == "jaden":
            file = "stuff/jaden_list.txt"
        elif type == "donger":
            file = "stuff/listofdongers.txt"
        try:
            return random.choice(list(open(file)))
        except:
            return "Error getting file {0}".format(file)

    def prerules(self):
        return #For modules which do things before the FIGHT has started, before the rules.
    def prefight(self):
        return #For modules which do things before the FIGHT has started, after the rules.
    def fightstart(self):
        return #For modules which do things after the FIGHT ascii, but before the fighting starts.
    def postfight(self):
        return #For modules which do things after the fight is over

    # For the record: cli = client and ev = event
    def _connect(self, cli, ev):
        # Starting with the SASL authentication
        # Note: If services are down, the bot won't connect
        cli.send("CAP REQ :sasl extended-join account-notify")
        cli.send("AUTHENTICATE PLAIN")

    def _ctcpreply(self, cli, ev):
        if ev.arguments[0] == "PING":
            if not self.lastpingreq:
                return
            
            current_milli_time = int(round(time.time() * 1000))
            diff = current_milli_time - int(ev.arguments[1])
            secs = str(diff / 1000)
            cli.privmsg(self.lastpingreq, "{0}: {1} seconds".format(ev.source, secs))
            self.lastpingreq = None
        
    def _join(self, cli, ev):
        if ev.source2.nick == cli.nickname and ev.target == self.primarychan:
            self.irc.privmsg(ev.target, "ヽ༼ຈل͜ຈ༽ﾉ RAISE YOUR DONGERS ヽ༼ຈل͜ຈ༽ﾉ")

    def _dusers(self, skip):
        players = self.health
        del players[skip]
        pplayers = []
        for i in players:
            pplayers.append(i.lower())
        ṕplayers = list(self.health)
        last = pplayers[-1]
        del pplayers[-1]
        return ", ".join(pplayers) + " and " + last
        
    def _auth(self, cli, ev):
        cli.send("AUTHENTICATE {0}".format(
        base64.b64encode("{0}\0{0}\0{1}".format(self.config['nickserv-user'],
                                                self.config['nickserv-pass'])
                                                .encode()).decode()))
        cli.send("CAP END")
    
    def _account(self, cli, ev):
        if ev.target == "*":
            ev.target = None
        for i in cli.channels:
            try:
                cli.channels[i].users[ev.source.nick.lower()].account = ev.target
            except:
                pass

    def _welcome(self, cli, ev):
        cli.join(self.config['channel'])
        for channel in self.auxchans:
           time.sleep(2)
           cli.join(channel)

    def _timeouts(self):
        while True:
            time.sleep(5)
            if self.gamerunning and self.turn != "":
                if time.time() - self.roundstart > 60:
                    self.irc.privmsg(self.primarychan, "\002{0}\002 forfeits due to idle.".format(self.turn))
                    self.irc.devoice(self.primarychan, self.turn)
                    self.countstat(self.turn, "idleout")
                    self.aliveplayers.remove(self.turn)
                    self.deadplayers.append(self.turn)
                    self.health[self.turn] = -1
                    if len(self.aliveplayers) == 1:
                        self.countstat(self.aliveplayers[0], "easywin")
                    self.getturn()
        

# Database stuff
database = peewee.SqliteDatabase('dongerdong.db')
database.connect()

class BaseModel(peewee.Model):
    class Meta:
        database = database

# NEW Stats table
class Statsv2(BaseModel):
    nick = peewee.CharField()  # NickServ account of the player
    realnick = peewee.CharField()  # Nickname of the player (not lowercased :P)
    wins = peewee.IntegerField() # Number of REKTs
    losses = peewee.IntegerField() # Number of loses
    quits = peewee.IntegerField() # Number of coward quits
    easywins = peewee.IntegerField() # Number of easy wins (player leaving, etc)
    fights = peewee.IntegerField() # !fight usage [only counted if it started a game]
    accepts = peewee.IntegerField() # !accept usage [only counted if the fight was started] (Total = !fight + !accept)
    dcaused = peewee.IntegerField() # Total amount of damage caused
    dreceived = peewee.IntegerField() # Total amount of damage received
    praises = peewee.IntegerField() # !praise usage
    idleouts = peewee.IntegerField() # >:(
    heals = peewee.IntegerField() # !heal usage
    hits = peewee.IntegerField() # !hit usage
    
Statsv2.create_table(True) # Here we create the table

# Start donging
dongerdong = Donger()

# Load modules
for module in dongerdong.config['modules']:
    # get tha modulah
    modulesb = getattr(__import__("modules.{0}".format(module)), module)
    
    # execute tah modulah functioh
    modulesb.loadModule(dongerdong) # and that's all

while dongerdong.irc.connected == True and dongerdong.irc.imayreconnect == True:
    try:
        time.sleep(1) # Infinite loop of awesomeness
    except KeyboardInterrupt:
        excuse=dongerdong.randomLine("excuse")
        #excuse=random.choice(list(open("excuse_list.txt"))) #Parsing an excuse list from BOFH
        # Sending stuff manually and assigning it the fucking top priority (no queue)
        # dongerdong.irc.send("PRIVMSG {0} :ERROR - {1}".format(dongerdong.chan, excuse), True)
        dongerdong.irc.send("QUIT :{0}".format(excuse.upper()), True)
        print("exit due to keyboard interrupt")
        break  # >:D PURE EVIL

