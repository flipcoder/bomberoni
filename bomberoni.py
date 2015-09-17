#!/usr/bin/env python2

import os
import sys
import pygame
from euclid import Vector2
import pytmx
from copy import copy
import random
import numpy
import math
import weakref
import six

random.seed()

TITLE = 'BOMBERONI'
#SCALE = 3
SCALE = 4
#SCREEN_W = 400
#SCREEN_H = 225
TILE_SZ = 16
TILE_SZ_T = (TILE_SZ*1.0,TILE_SZ*1.0)
#SCREEN_SZ = (SCREEN_W, SCREEN_H)
SCALED_SZ = (1366,768)
SCREEN_SZ = (SCALED_SZ[0] // SCALE, SCALED_SZ[1] // SCALE)
#SCALED_SZ = (SCREEN_W * SCALE, SCREEN_H * SCALE)
FONT = './data/fonts/Early GameBoy.ttf'
TRANS = (255,0,255)
EPSILON = 1 ** -4

AXES = (6,7)

def sgn(a):
    return (a > 0) - (a < 0)

def load_image(fn):
    img = pygame.image.load(fn).convert()
    img.set_colorkey(TRANS)
    return img

def tileset(fn, **kwargs):
    img = load_image(fn)
    w, h = img.get_size()
    tiles = []
    hflip = kwargs.get('hflip', False)
    vflip = kwargs.get('vflip', False)
    for i in xrange(0, w, h):
        tiles += [img.subsurface((i,0,h,h))]
        tiles[-1] = pygame.transform.flip(tiles[-1], hflip, vflip)
        tiles[-1].set_colorkey(TRANS)
    return tiles

class Role:
    Local = 0
    Server = 1
    Client = 2

class Object(object):
    def __init__(self, **kwargs):
        self.game = kwargs.get('game')
        self.attached = False
        
        self.pos = Vector2(*kwargs.get('pos', (0.0, 0.0)))
        self.ofs = Vector2(*kwargs.get('ofs', (0.0, 0.0)))
        self.vel = Vector2(*kwargs.get('vel', (0.0, 0.0)))
        self.sz = Vector2(*kwargs.get('sz'))
        self.surface = kwargs.get('surface', None)
        self.surfaces = kwargs.get('surfaces', None)
        if isinstance(self.surfaces, str):
            self.surfaces = tileset(self.surfaces)
        if self.surfaces and len(self.surfaces):
            self.surface = self.surfaces[0]
        self.solid = kwargs.get('solid', True)
        self.breakable = kwargs.get('breakable', False)
        self.origin = Vector2(kwargs.get('origin', (0.0,self.sz.y)))
        self.depth = kwargs.get('depth', 1 if self.solid else 0)
        self.owner = kwargs.get('owner', None)
        if self.owner and not isinstance(self.owner, weakref.ref):
            self.owner = weakref.ref(self.owner)
        self.hurt = kwargs.get('hurt', False)

    def rect(self):
        assert self.sz.x > EPSILON
        assert self.sz.y > EPSILON
        return pygame.Rect(self.pos.x, self.pos.y, int(round(self.sz.x)), int(round((self.sz.y))))
    
    def mask(self):
        return self.rect()
    
    def logic(self, t):
        if self.vel.magnitude() >= EPSILON:
            self.pos += self.vel * t
        
        if self.pos.x < -self.sz.x or self.pos.x >= self.game.world.sz.x:
            self.attached = False
        elif self.pos.y < -self.sz.y or self.pos.y >= self.game.world.sz.y:
            self.attached = False
    
    def render(self, view):
        assert self.surface
        if self.attached and self.surface:
            self.game.screen.buf.blit(self.surface, self.pos + self.ofs - view)

    def collision(self):
        objs = self.game.world.objects
        objs = filter(lambda x: x != self and x.attached, objs)
        objs = filter(lambda x: x.solid, objs)
        objs = map(lambda x: x.mask(), objs)
        if -1 != self.mask().collidelist(objs):
            return True
        return False
    
    def colliders(self):
        cols = []
        objs = self.game.world.objects
        objs = filter(lambda x: x != self and x.attached, objs)
        for o in objs:
            if self.mask().colliderect(o.mask()):
                cols += [o]
        return cols

class Item(Object):

    Bomb = 0
    Kick = 1
    Multi = 2
    Curse = 3
    Flame = 4
    Remote = 5
    
    def __init__(self, item_id, **kwargs):
        super(self.__class__, self).__init__(**kwargs)
        
        if isinstance(self.surface, list):
            self.surfaces = self.surface
            self.surface = self.surfaces[0]
            self.animate = True
            self.anim_point = 0.0
            self.anim_speed = 4.0
        else:
            self.animate = False
        
        self.life = 0.0
        self.item_id = item_id
        self.depth = 1
        
    def logic(self,t):
        
        bobspeed = 2.0
        self.life = math.fmod(self.life + t, bobspeed)
        self.ofs = Vector2(0.0, math.sin(self.life*bobspeed*2.0*math.pi))

        if self.animate:
            self.anim_point += t * self.anim_speed
            if self.anim_point >= len(self.surfaces)-1:
                self.anim_point = 0.0
            a = int(round(self.anim_point))
            self.surface = self.surfaces[a]
    
class Wall(Object):
    def __init__(self, **kwargs):
        super(self.__class__, self).__init__(**kwargs)
    
    def explode(self):
        if self.breakable:
            item = self.game.world.random_item(game=self.game, pos=self.pos, sz=TILE_SZ_T, solid=False)
            if item:
                self.game.world.attach(item)
            self.attached = False

class Screen(Object):
    def __init__(self,screen,**kwargs):
        super(self.__class__, self).__init__(**kwargs)
        
        self.pos = Vector2(0.0, 0.0)
        self.sz = Vector2(SCREEN_SZ[0], SCREEN_SZ[1])
        self.buf = pygame.Surface(SCREEN_SZ).convert()
        self.surface = pygame.Surface(SCALED_SZ).convert()
        self.screen = screen
    
    def render(self):
        pygame.transform.scale(self.buf, SCALED_SZ, self.surface)
        self.screen.blit(self.surface, (0,0))

class Splode(Object):
    def __init__(self, **kwargs):
        super(self.__class__, self).__init__(**kwargs)
        
        self.surfaces = self.game.world.splode
        
        self.anim_point = 0.0
        self.anim_speed = 8.0
        self.frames = {
            "default": [0,1,2,3,4,5]
        }
        self.state = "default"
        self.surface = self.surfaces[self.frames[self.state][0]]
        self.solid = False
        self.hurt = True

        #self.life = 0.0

    def logic(self, t):

        #self.life += t
        #if self.life >= 1.0:
        #    self.attached = False
        
        self.anim_point += t * self.anim_speed
        if self.anim_point >= len(self.frames[self.state])-1:
            self.anim_point = 0.0
            self.attached = False
        a = int(round(self.anim_point))
        self.surface = self.surfaces[self.frames[self.state][a]]
    
class Bomb(Object):
    def __init__(self, fast=False, modern=False, **kwargs):
        super(self.__class__, self).__init__(**kwargs)
        
        self.modern = modern
        
        if modern:
            self.surfaces = self.game.world.bomb_modern
        else:
            self.surfaces = self.game.world.bomb
        
        self.anim_point = 0.0
        self.anim_speed = 4.0
        self.frames = {
            "default": [0,1]
        }
        self.state = "default"
        self.surface = self.surfaces[self.frames[self.state][0]]
        self.breakable = True

        self.life = 2.5
        if fast:
            self.life /= 2.0
        
        if self.owner:
            # object ctor should ensure self.owner is weakref
            assert isinstance(self.owner, weakref.ref)
            owner = self.owner()
            self.radius = owner.get_radius() if owner else 1
        else:
            self.radius = 1

    def explode(self):
        
        self.snap()
        self.vel = Vector2(0.0, 0.0)
        self.attached = False
            
        self.game.world.attach(Splode(game=self.game, pos=self.pos, sz=TILE_SZ_T, owner=self.owner))
        
        offset = [
            Vector2(TILE_SZ, 0.0),
            Vector2(-TILE_SZ, 0.0),
            Vector2(0.0, -TILE_SZ),
            Vector2(0.0, TILE_SZ)
        ]
        
        def cb(x):
            if x.attached and x.breakable:
                x.explode()
            return x.breakable
            
        fail_cb = lambda x: x.solid and not x.breakable
        
        if self.owner:
            owner = self.owner()
            radius = owner.get_radius() if owner else self.radius
        else:
            radius = 1
        
        for d in range(len(offset)):
            for rad in range(1,radius+1):
                p = self.pos + (offset[d] * rad)
                s = Splode(game=self.game, pos=p, sz=TILE_SZ_T, owner=self.owner)
                o = self.game.world.overwrite(s, cb=cb, fail_cb=fail_cb)
                if o:
                    break
        
        return True
    

    def snap(self):
        self.pos = Vector2(
            float((self.pos.x+TILE_SZ/2.0)//TILE_SZ*TILE_SZ),
            float((self.pos.y+TILE_SZ/2.0)//TILE_SZ*TILE_SZ)
        )
        
    def logic(self, t):

        old_pos = copy(self.pos)
        super(self.__class__,self).logic(t)
        
        cols = self.colliders()
        
        if len(cols):
            self.vel = Vector2(0.0,0.0)
            self.pos = copy(old_pos)
            self.snap()
        
        self.life -= t
        if self.life <= 0.0:
            if self.explode():
                self.game.play(self.game.splode_snd)
                return
        
        self.anim_point += t * self.anim_speed
        if self.anim_point >= len(self.frames[self.state])-1:
            self.anim_point = 0.0
        a = int(round(self.anim_point))
        self.surface = self.surfaces[self.frames[self.state][a]]
        
class Curse:
    NoCurse = 0
    Slow = 1
    Fast = 2
    Slippery = 3
    NoPlant = 4
    SmallBlast = 5
    FastBomb = 6
    AlwaysPlant = 7
    SwapPlayer = 8
    Max = 9

class Guy(Object):
    SPEED = 55.0
    
    def __init__(self, **kwargs):
        super(self.__class__, self).__init__(**kwargs)
        
        self.profile = kwargs.get('profile')
        
        fn = './data/gfx/bomber-army.png'
        self.surfaces = tileset(fn)
        self.surfaces += tileset(fn, hflip=True)[6:13]

        if self.profile.color != (255,255,255):
            for s in self.surfaces:
                s.lock()
                for y in xrange(s.get_height()):
                    for x in xrange(s.get_width()):
                        player_col = pygame.Color(
                            self.profile.color[0],
                            self.profile.color[1],
                            self.profile.color[2],
                            255
                        )
                        pxc = copy(s.get_at((x,y)))
                        if pxc != pygame.Color(255,0,255):
                            mix = 0.5
                            pxc.r = int((mix*(player_col.r/255.0) + (1.0-mix)*(pxc.r/255.0)) * 255)
                            pxc.g = int((mix*(player_col.g/255.0) + (1.0-mix)*(pxc.g/255.0)) * 255)
                            pxc.b = int((mix*(player_col.b/255.0) + (1.0-mix)*(pxc.b/255.0)) * 255)
                            s.set_at((x,y), pxc)
                s.unlock()
        
        self.frames = {
            "down": [0,1,2,1,3,4,5,4],
            "up": [12,13,14,13,15,16,17,16],
            #"right": [18,19,20,19,21,22,23,22],
            "right": [21,22,23,22,24,25,26,25],
            "left": [6,7,8,7,9,10,11,10],
            "death": [18,19,20]
        }
        #self.surfaces += tileset(fn, hflip=True)[3:6]
        #self.frames = {
        #    "down": [0,1,0,2],
        #    "up": [6,7,6,8],
        #    "left": [9,10,9,11],
        #    "right": [3,4,3,5]
        #}
        self.anim_point = 0.0
        self.state = "down"
        self.normal_anim_speed = 12.0
        self.death_anim_speed = 12.0
        self.anim_speed = self.normal_anim_speed
        self.surface = self.surfaces[self.frames[self.state][0]]
        self.speed = Guy.SPEED
        self.origin = Vector2(TILE_SZ*.5,TILE_SZ*.75)
        self.solid = False
        self.depth = 1
        self.radius = 1
        self.frozen = False # disallow movement
        self.bombs = 1
        self.kick = False
        self.multi = False
        self.remote = False
        #self.last_bomb = None
        self.curse_time = 0.0
        self.curse = None
        self.last_vel_intent = Vector2()
        self.old_pos = self.pos

    def get_radius(self):
        if self.curse == Curse.SmallBlast:
            return 1
        return self.radius
        
    def kill(self):
        self.frozen = True
        self.state = "death"
        self.anim_speed = 2.0
        self.game.play(self.game.death_snd)
    
    def curse_logic(self,t):
        if not self.curse:
            return
        self.curse_time -= t
        if self.curse_time <= 0.0:
            self.stop_curse()
    
    def do_curse(self):
        self.stop_curse()
        self.curse  = random.randint(1,Curse.Max-1)
        self.curse_time = 10.0
        if self.curse == Curse.Slow:
            self.speed = Guy.SPEED / 2.0
        elif self.curse == Curse.Fast:
            self.speed = Guy.SPEED * 2.0
        elif self.curse == Curse.SwapPlayer:
            players_on_map = filter(lambda x:
                x.attached and isinstance(x, Guy) and x != self, self.game.world.objects
            )
            if len(players_on_map) >= 1:
                random_player = random.choice(players_on_map)
                self.pos, random_player.pos = random_player.pos, self.pos
                self.old_pos, random_player.old_pos = random_player.old_pos, self.old_pos
            self.stop_curse() # no persist
    
    def stop_curse(self):
        if not self.curse:
            return
        if self.curse == Curse.Slow:
            self.speed = Guy.SPEED
        self.curse = None
        self.curse_time = 0.0

    def give(self, item):
        if item.item_id == Item.Bomb:
            self.bombs += 1
        elif item.item_id == Item.Kick:
            self.kick = True
        elif item.item_id == Item.Multi:
            self.multi = True
        elif item.item_id == Item.Curse:
            self.do_curse()
        elif item.item_id == Item.Flame:
            self.radius += 1
        elif item.item_id == Item.Remote:
            self.remote = True
    
    def get_my_bombs(self):
        return filter(lambda x:
            x.attached and isinstance(x, Bomb) and x.owner and x.owner()==self,
            self.game.world.objects) 
    
    def plant(self, ofs = Vector2()):
        if self.curse == Curse.NoPlant:
            return None
        
        my_bombs = self.get_my_bombs()

        # when player runs out of bombs, disallow planting
        if len(my_bombs) >= self.bombs:
            return None
        
        # snaps plant position to grid
        p = (self.pos + self.origin + ofs) // int(TILE_SZ) * int(TILE_SZ)
        
        b = Bomb(
            fast=(self.curse==Curse.FastBomb),modern=self.remote,
            game=self.game, pos=p, sz=TILE_SZ_T, solid=True, owner=self)
        r = self.game.world.place(b)
        if r:
            #self.last_bomb = weakref.ref(b)
            self.game.play(self.game.place_snd)
            return b
        return None
    
    def dir_vec(self):
        try:
            return {
                "left": Vector2(-1.0, 0.0),
                "right": Vector2(1.0, 0.0),
                "up": Vector2(0.0, -1.0),
                "down": Vector2(0.0, 1.0)
            }[self.state]
        except KeyError:
            return None
        
    def multiplant(self):
        if self.curse == Curse.NoPlant:
            return None
        
        d = self.dir_vec() * TILE_SZ
        if not d:
            return False
        ofs = copy(d)
        i = 0
        while self.plant(ofs):
            ofs += d
            i += 1
        return i > 0
    
    def logic(self, t):

        self.curse_logic(t)
        
        self.cols = self.colliders()
        self.solid_cols = filter(lambda x: x.solid, self.cols)
        self.snapped_cols = []
        
        v = Vector2(0.0, 0.0)
        self.vel_intent = Vector2(0.0, 0.0)
        if not self.frozen:
            if self.profile.btn('left'):
                v.x -= self.speed
                self.state = "left"
            elif self.profile.btn('right'):
                v.x += self.speed
                self.state = "right"
            if self.profile.btn('up'):
                v.y -= self.speed
                self.state = "up"
            elif self.profile.btn('down'):
                v.y += self.speed
                self.state = "down"

            if self.curse == Curse.Slippery:
                if v.magnitude() <= EPSILON:
                    v = copy(self.last_vel_intent)
            
            if v.magnitude() >= EPSILON:
                
                v.normalize()
                v *= self.speed
                
                # collision
                self.old_pos = copy(self.pos)
                self.vel = v
                self.vel_intent = copy(v)
                self.last_vel_intent = copy(v)
                
                if abs(self.vel) >= EPSILON:
                    self.pos += self.vel * t
                    if self.snap():
                        self.pos.x += self.vel.x * t
                        if self.snap():
                            self.pos.y += self.vel.y * t
                            if self.snap():
                                self.vel = Vector2(0.0, 0.0)
                
        
        self.vel = v

        bad_objs = filter(lambda x: x.hurt, self.cols)
        if bad_objs:
            self.frozen = True
            self.kill()

        for col in self.cols:
            if isinstance(col, Item):
                self.game.play(self.game.item_snd)
                self.give(col)
                col.attached = False

        for col in self.snapped_cols:
            if not col.attached:
                continue
            if isinstance(col, Bomb):
                if self.kick and not self.remote:
                    if self.vel_intent.magnitude() >= EPSILON:
                        col.vel = copy(self.vel_intent) * 2.0
                        self.game.play(self.game.kick_snd)

        self.cols = self.colliders()

        if self.pos.x < -self.sz.x or self.pos.x >= self.game.world.sz.x:
            self.kill()
        elif self.pos.y < -self.sz.y or self.pos.y >= self.game.world.sz.y:
            self.kill()

        if not self.frozen:
            btn = self.profile.btn(0)
            if self.curse == Curse.AlwaysPlant or btn:
                multiplanted = False
                if self.multi:
                    # require explicit holding of button for multiplant during alwaysplant curse
                    if btn or not self.curse == Curse.AlwaysPlant:
                        for col in self.cols:
                            if isinstance(col, Bomb):
                                if self.multiplant():
                                    multiplanted = True
                                    self.game.play(self.game.place_snd)
                                    self.profile.btn(0, consume=True)
                                    break
                
                if not multiplanted:
                    # try to plant bomb (normal planting behavior)
                    if self.plant():
                        self.profile.btn(0, consume=True)
            elif self.profile.btn(1):
                #if self.last_bomb:
                #    b = self.last_bomb()
                #    if b:
                my_bombs = self.get_my_bombs()

                stopped_bomb = False
                for b in my_bombs:
                    if b.vel.magnitude() > EPSILON:
                        self.profile.btn(1, consume=True)
                        # stop a moving bomb
                        self.game.play(self.game.kick_snd)
                        b.vel = Vector2()
                        b.snap()
                        stopped_bomb = True
                
                if not stopped_bomb:
                    for b in my_bombs:
                        if self.remote:
                            self.profile.btn(1, consume=True)
                            # already stopped and have remote? detonate!
                            self.game.play(self.game.detonate_snd)
                            b.explode()
        
        if self.vel.magnitude() > 0.0 or self.state == "death":
            self.anim_point += t * self.anim_speed
            if self.anim_point >= len(self.frames[self.state])-1:
                if self.state == "death":
                    self.attached = False
                    return
                self.anim_point = 0.0
            a = int(round(self.anim_point))
            self.surface = self.surfaces[self.frames[self.state][a]]
        else:
            self.anim_point = 0.0
            a = int(round(self.anim_point))
            self.surface = self.surfaces[self.frames[self.state][a]]
        
    def snap(self):
        objs = self.game.world.objects
        objs = filter(lambda x: x != self and x.solid and x.attached, objs)
        objs = filter(lambda x: x not in self.solid_cols, objs)
        objs = map(lambda x: x.mask(), objs)
        if -1 != self.mask().collidelist(objs):
            self.snapped_cols += self.colliders()
            self.snapped_cols = list(set(self.snapped_cols))
            self.pos = copy(self.old_pos) # snap
            return True
        return False

    def mask(self):
        return pygame.Rect(
            self.pos.x+self.sz.x/4.0, 
            self.pos.y+self.sz.y/2.0,
            int(round(self.sz.x/2.0)),
            int(round((self.sz.y/2.0)))
        )

    #def render(self, view):
    #    self.game.screen.buf.blit(self.surface, self.pos - view)

#class Tile(Object):
#    def __init__(self, surface, **kwargs):
#        super(self.__class__, self).__init__(**kwargs)
#        self.surface = surface
#    def render(self, view):
#        self.game.screen.buf.blit(self.surface, self.pos - view)

class World:
    def __init__(self, game):
        #self.tmx = pytmx.util_pygame.load_pygame(fn)
        #for img in self.tmx.images:
        #    if img:
        #        img.set_colorkey(TRANS)
        self.sz = Vector2(
            SCREEN_SZ[0], SCREEN_SZ[1]
            #self.tmx.width * self.tmx.tilewidth,
            #self.tmx.height * self.tmx.tileheight
        )
        self.ofs = Vector2()
        
        line = []
        self.game = game
        self.game.world = self
        self.objects = []
        self.wall = load_image('data/gfx/concrete-gray-solid.png')
        self.bwall = load_image('data/gfx/concrete-gray-breakable.png')
        self.bomb = tileset('data/gfx/bomb-toon.png')
        self.bomb_modern = tileset('data/gfx/bomb-modern.png')
        self.splode = tileset('data/gfx/explosion-toon.png')
        self.bomb_inc = load_image('data/gfx/powerup-bomb-increment.png')
        self.kick = load_image('data/gfx/powerup-bomb-kick.png')
        self.multibomb = load_image('data/gfx/powerup-bomb-multibomb.png')
        self.curse = load_image('data/gfx/powerup-curse.png')
        self.flame = tileset('data/gfx/powerup-explosion.png')
        self.remote = tileset('data/gfx/powerup-bomb-remote.png')
        
        self.w = int(SCREEN_SZ[0] / TILE_SZ)
        if self.w % 2 == 0:
            self.ofs = Vector2(-TILE_SZ/2,0.0)
            self.w -= 1
        self.h = int(SCREEN_SZ[1] / TILE_SZ - 1)
        if self.h % 2 == 0:
            self.h -= 1
        w = self.w
        h = self.h

        self.splode = tileset('data/gfx/explosion-toon.png')
        self.items = [
            [lambda **kwargs: Item(Item.Bomb, surface=self.bomb_inc, **kwargs), 2.0],
            [lambda **kwargs: Item(Item.Flame, surface=self.flame, **kwargs), 2.0],
            [lambda **kwargs: Item(Item.Curse, surface=self.curse, **kwargs), 1.0],
            [lambda **kwargs: Item(Item.Kick, surface=self.kick, **kwargs), 0.5],
            [lambda **kwargs: Item(Item.Multi, surface=self.multibomb, **kwargs), 0.5],
            [lambda **kwargs: Item(Item.Remote, surface=self.remote, **kwargs), 0.5]
        ]

        self.items, self.items_p = zip(*self.items)
        s = sum(self.items_p)
        self.items_p = map(lambda x: x / s, self.items_p)
        
        for j in range(0, self.h):
            for i in range(0, self.w):
                if i==0 or j==0 or i==w-1 or j==h-1:
                    obj = Wall(game=game, pos=(i*TILE_SZ*1.0, j*TILE_SZ*1.0), sz=TILE_SZ_T, surface=self.wall, solid=True)
                    self.attach(obj)
                elif i%2==0 and j%2==0:
                    obj = Wall(game=game, pos=(i*TILE_SZ*1.0, j*TILE_SZ*1.0), sz=TILE_SZ_T, surface=self.wall, solid=True)
                    self.attach(obj)
                elif random.random() < 0.8:
                    
                    # don't sprinkle in spawns
                    if i==1 and 1<=j<=3 or j==1 and 1<=i<=3:
                        continue
                    if i==w-2 and 1<=j<=3 or j==1 and w-4<=i<=w-2:
                        continue
                    if i==w-2 and h-4<=j<=h-2 or j==h-2 and w-4<=i<=w-2:
                        continue
                    if i==1 and h-4<=j<=h-2 or j==h-2 and 1<=i<=3:
                        continue
                    
                    obj = Wall(game=game, pos=(i*TILE_SZ*1.0, j*TILE_SZ*1.0), sz=TILE_SZ_T,surface=self.bwall, solid=True, breakable=True)
                    self.attach(obj)
        
        #self.spawns = []
        #for layer in self.tmx.visible_layers:
        #    if isinstance(layer, pytmx.TiledObjectGroup):
        #        for obj in layer:
        #            if obj.name == 'S':
        #                self.spawns += [obj]

        self.next_level = False
        
    def attach(self, obj):
        if not obj.attached:
            self.objects += [obj]
            obj.attached = True
        
    def place(self, obj):
        if not obj.attached:
            objs = self.objects
            
            objs = filter(lambda x: x.solid, objs)
            objs = map(lambda x: x.mask(), objs)
            
            if -1 != obj.mask().collidelist(objs):
                return False
            
            self.attach(obj)
            return True

    def overwrite(self, obj, cb=None, fail_cb=None):
        if not obj.attached:
            objs = self.objects
            
            objs = filter(lambda x: x.solid, objs)
            
            obj_masks = map(lambda x: x.mask(), objs)

            matches = obj.mask().collidelistall(obj_masks)
            overwritten = []
            
            if fail_cb:
                for r in matches:
                    if fail_cb(objs[r]):
                        return fail_cb
            
            for r in matches:
                if not cb or cb(objs[r]):
                    try:
                        self.objects.remove(objs[r])
                        overwritten += [objs[r]]
                    except ValueError:
                        pass
            
            self.attach(obj)
            return overwritten

    def random_item(self, **kwargs):
        if random.random() < 0.25:
            item = numpy.random.choice(self.items, p=self.items_p)
            return item(**kwargs)
        return None
        
    def logic(self):
        pass
        #if self.next_level:
        #    self.game.level += 1
        #    self.next_level = False
        #    self.game.reset()
        
    def render(self, view):
        #tw = self.tmx.tilewidth
        #th = self.tmx.tileheight
        #for layer in self.tmx.visible_layers:
        #    if isinstance(layer, pytmx.TiledTileLayer):
        #        for x, y, img in layer.tiles():
        #            self.game.screen.buf.blit(img, (x*tw-view.x, y*th-view.y))

        for obj in self.objects:
            obj.render(self.ofs - view)

def render_order(a,b):
    v = (a.pos.y + a.depth*10000) - (b.pos.y + b.depth*10000)
    return int(round(v))

class Joystick(object):
    def __init__(self, num, joy=None):
        self.num = num
        self.joy = joy # pygame joy
        self.btn_ = [False] * joy.get_numbuttons()
        self.axis_ = [0.0] * joy.get_numaxes()
        self.axis_consumed_ = [False] * 2 * joy.get_numaxes()
        self.hat_ = [False] * 4 * joy.get_numhats()
        self.threshold = 0.5
    def btn(self, b, v=None, consume=False):
        try:
            if v == None:
                v = self.btn_[b]
                if consume:
                    self.btn_[b] = False
                return v
            self.btn_[b] = v
        except IndexError:
            return False
    def axis_crit(self, b, v=None, consume=False):
        """
        Is an axis passed its threshold?
        """
        try:
            if v == None:
                
                if self.axis_[b] < -self.threshold:
                    c = self.axis_consumed_[b*2] # was consumed?
                    if consume:
                        self.axis_consumed_[b*2] = True
                    return -1 if not c else 0
                elif self.axis_[b] > self.threshold:
                    c = self.axis_consumed_[b*2+1] # was consumed?
                    if consume:
                        self.axis_consumed_[b*2+1] = True
                    return 1 if not c else 0
                else:
                    self.axis_consumed_[b*2] = False
                    self.axis_consumed_[b*2+1] = False
                    return 0

                #if self.axis_[b] < -self.threshold:
                #    was = self.axis_crit_[b*2]
                #    self.axis_crit_[b*2] = not consume
                #    self.axis_crit_[b*2+1] = False
                #    return -1 if was>=0 else 0
                #elif self.axis_[b] > self.threshold:
                #    was = self.axis_crit_[b*2+1]
                #    self.axis_crit_[b*2] = False
                #    self.axis_crit_[b*2+1] = not consume
                #    return 1 if was<=0 else 0
                #else:
                #    self.axis_crit_[b*2] = False
                #    self.axis_crit_[b*2+1] = False
                #    return 0

            self.axis_[b] = v
        except IndexError:
            return 0
    def axis(self, b, v=None):
        try:
            if v == None:
                return self.axis_[b]
            self.axis_[b] = v
        except IndexError:
            return 0.0
    def hat(self, b, v=None, consume=False):
        try:
            if v == None:
                v = self.hat_[b]
                if consume:
                    self.hat_[b] = False
                return v
            self.hat_[b] = v
        except IndexError:
            return False
        
class Profile(object):
    def __init__(self, game, num, joy=None):
        self.game = game
        self.num = num
        self.score = 0
        self.client = None
        if num == 0:
            self.color = (0xFF, 0xFF, 0xFF)
        elif num == 1:
            self.color = (0x0, 0x0, 0x0)
        elif num == 2:
            self.color = (0xFF, 0xFF, 0x0)
        elif num == 3:
            self.color = (0x00, 0x00, 0xFF)
        self.joy = joy
    
    def btn(self, b, consume=False):
        
        r = False
        
        if self.joy:
            if isinstance(b, int):
                r = self.joy.btn(b, consume=consume)
                if b == 0:
                    if not r and ord(' ') in self.game.keys:
                        r = True
                        self.game.keys.remove(ord(' '))
                elif b == 1:
                    if not r and ord('a') in self.game.keys:
                        r = True
                        self.game.keys.remove(ord('a'))
            elif b == 'left':
                r = self.joy.axis(AXES[0]) < -0.5 or self.joy.hat(0) or ord('j') in self.game.keys
            elif b == 'right':
                r = self.joy.axis(AXES[0]) > 0.5 or self.joy.hat(1) or ord('l') in self.game.keys
            elif b == 'up':
                r = self.joy.axis(AXES[1]) < -0.5 or self.joy.hat(2) or ord('i') in self.game.keys
            elif b == 'down':
                r = self.joy.axis(AXES[1]) > 0.5 or self.joy.hat(3) or ord('k') in self.game.keys
            
            if r:
                return r
        
        # temp keys
        if self.num == 0:
            k = set(map(lambda x: ord(x), ('i','k','j','l',' '))) & set(self.game.keys)

            if b == 0:
                r = ' ' in k
                if r:
                    self.game.keys.remove(ord(' '))
            elif b == 'left':
                r = 'j' in k
            elif b == 'right':
                r = 'l' in k
            elif b == 'up':
                 r = 'i' in k
            elif b == 'down':
                r = 'k' in k
        
        return r

class Mode(object):
    def __init__(self):
        pass
    def logic(self,t):
        pass
    def render(self):
        pass

class GameMode(Mode):
    def __init__(self, game, role=Role.Local):
        self.game = game
        self.world = World(self.game)
        self.role = role
        
        self.guys = []
        self.reset()

        self.game.play(self.game.play_snd)

    def reset(self):
        
        for guy in self.guys:
            if guy:
               guy.attached = False
        
        self.clean()
        
        self.guys = []
        self.sessions = []
        spawns = (
            (TILE_SZ*1.0, TILE_SZ*1.0),
            (TILE_SZ*1.0, (self.world.h-2)*TILE_SZ*1.0),
            ((self.world.w-2)*TILE_SZ*1.0, TILE_SZ*1.0),
            ((self.world.w-2)*TILE_SZ*1.0, (self.world.h-2)*TILE_SZ*1.0)
        )
        
        for i in range(len(self.game.profiles)):
            if self.game.profiles[i]:
                g = Guy(profile=self.game.profiles[i], game=self.game, mode=self, pos=spawns[i], sz=TILE_SZ_T)
                self.guys.append(g)
                self.world.attach(g)
        
    def clean(self):
        self.world.objects = filter(lambda o: o.attached, self.world.objects)
        
    def logic(self,t):
        
        self.world.logic()

        # end condition
        guys_left = filter(lambda x: x.attached, self.guys)
        guy_count = len(guys_left)
        if guy_count == 0:
            self.reset()
        elif guy_count == 1:
            guys_left[0].profile.score += 1
            self.reset()
        
        self.clean()
        for obj in self.world.objects:
            obj.logic(t)
        self.world.objects.sort(cmp=render_order)
    
    def render(self):
        self.game.screen.buf.fill((0,128,0))
        scr = self.game.screen
        f = self.game.font
        i = 0
        for p in self.game.profiles:
            if not p:
                continue
            pos = ((i+1)*SCREEN_SZ[0]/(len(self.game.profiles)+1), SCREEN_SZ[1] - self.game.font_size)
            text_center(scr, f, str(p.score), col=p.color, n=0, pos=pos)
            i += 1
        self.world.render((0.0, 0.0))

def text_center(scr, font, text, n=1, col=(0xFF,0xFF,0xFF), pos=(0,0), shadow=None):
    tx = font.render(text, n, col)
    if shadow:
        tx_s = font.render(text, n, (0,0,0))
        scr.buf.blit(
            tx_s,
            (
                shadow[0] + pos[0] - tx.get_rect().w/2,
                pos[1] + shadow[1]
            )
        )

    scr.buf.blit(
        tx, (pos[0] - tx.get_rect().w/2, pos[1])
    )

class MenuMode(Mode):
    def __init__(self,game):
        self.game = game
        self.choice = 0
        self.ops = [
            "play",
            "join",
            "host",
            # text, current, min, max ([min,max])
            ["players: %s", 4, 2, 4],
            "quit"
        ]
        
    def select(self):
        if self.choice == 0:
            self.game.mode = GameMode(self.game)
        elif self.choice == 1:
            pass
        elif self.choice == 2:
            pass
        elif self.choice == 3:
            pass
        elif self.choice == 4:
            self.game.done = True
        
    def logic(self,t):
        
        if ord(' ') in self.game.keys:
            self.select()
            self.game.keys.remove(ord(' '))
        
        if isinstance(self.ops[self.choice],list):
            if pygame.K_j in self.game.keys:
                self.ops[self.choice][1] = max(self.ops[self.choice][1]-1,self.ops[self.choice][2])
                self.game.profile_count(self.ops[self.choice][1])
                self.game.keys.remove(pygame.K_j)
            elif pygame.K_l in self.game.keys:
                self.ops[self.choice][1] = min(self.ops[self.choice][1]+1,self.ops[self.choice][3])
                self.game.profile_count(self.ops[self.choice][1])
                self.game.keys.remove(pygame.K_l)
            
        if pygame.K_i in self.game.keys:
            self.choice = max(0,self.choice-1)
            self.game.keys.remove(pygame.K_i)
        if pygame.K_k in self.game.keys:
            self.choice = min(len(self.ops)-1, self.choice+1)
            self.game.keys.remove(pygame.K_k)

        j = index(self.game.joys,0)
        
        if not j:
            return
        
        r = j.axis_crit(AXES[1], consume=True)
        if r < 0:
            self.choice = max(0,self.choice-1)
        elif r > 0:
            self.choice = min(len(self.ops)-1, self.choice+1)
        
        if j.btn(0, consume=True):
            self.select()
    
    def render(self):
        self.game.screen.buf.fill((0,128,0))
        scr = self.game.screen
        f = self.game.font
        text_center(scr, f, "BOMBERONI", pos=(SCREEN_SZ[0]/2,32), shadow=(-1,-1))
        i = 0
        
        for op in self.ops:
            o = op
            if isinstance(op,list):
                o = op[0] % op[1]
            
            if i==self.choice:
                col = (0,0xFF,0)
            else:
                col = (0xFF,0xFF,0xFF)
            text_center(scr, f, o, col=col,
                pos=(
                    SCREEN_SZ[0]/2,
                    self.game.font_size*8+i*self.game.font_size),
                shadow=(-1,1))
            i += 1


def index(col, i):
    try:
        return col[i]
    except:
        return None

class Engine:
    def __init__(self):
        pygame.init()
        pygame.mixer.init(channels=8)

        self.play_snd = pygame.mixer.Sound('./data/sfx/play.wav')
        self.place_snd = pygame.mixer.Sound('./data/sfx/place.wav')
        self.death_snd = pygame.mixer.Sound('./data/sfx/death.wav')
        self.kick_snd = pygame.mixer.Sound('./data/sfx/kick.wav')
        self.splode_snd = pygame.mixer.Sound('./data/sfx/splode.wav')
        self.item_snd = pygame.mixer.Sound('./data/sfx/item.wav')
        self.detonate_snd = pygame.mixer.Sound('./data/sfx/detonate.wav')

        pygame.joystick.init()
        
        self.joys = []
        idx = 0
        for i in range(pygame.joystick.get_count()):
            joy = None
            try:
                joy = pygame.joystick.Joystick(idx)
            except:
                continue
            if not joy:
                continue
            joy.init()
            self.joys += [Joystick(i, joy)]
            idx+=1

        self.profile_count(4)
        
        pygame.display.set_caption(TITLE)
        self.screen = Screen(pygame.display.set_mode(SCALED_SZ, pygame.DOUBLEBUF), sz=SCREEN_SZ)
        self.font_size = SCALED_SZ[0]/100
        self.font = pygame.font.Font(FONT, self.font_size)
        self.clock = pygame.time.Clock()
        self.keys = []
        if len(sys.argv) >= 2:
            self.level = sys.argv[1]
        else:
            self.level = 1
        
        self.mode = MenuMode(self)
        
        self.chans = []
        for cid in range(8):
            self.chans += [pygame.mixer.Channel(cid)]
        
        self.next_chan = 0

    def play(self,snd):
        self.chans[self.next_chan].play(snd)
        self.next_chan += 1
        self.next_chan %= len(self.chans)
    
    def profile_count(self, n):
        
        self.profiles = []
        
        for i in range(n):
            self.profiles += [
                Profile(self,i,index(self.joys,i)),
            ]

    def __call__(self):
        
        self.done = False
        while True:
            t = self.clock.tick(60)*0.001
            self.logic(t)
            if self.done:
                break
            self.render()
            self.draw()
        
        return 0
       
    def logic(self, t):
        
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.done = True
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    self.done = True
                elif ev.key == pygame.K_r:
                    self.reset()
                if ev.key not in self.keys:
                    self.keys += [ev.key]
                if ev.key == pygame.K_PAGEUP:
                    self.world.next_level = True
            elif ev.type == pygame.KEYUP:
                try:
                    self.keys.remove(ev.key)
                except ValueError:
                    pass
            elif ev.type == pygame.JOYAXISMOTION:
                j = filter(lambda j: j.num == ev.joy, self.joys)[0]
                j.axis(ev.axis, ev.value)
            elif ev.type == pygame.JOYHATMOTION:
                j = filter(lambda j: j.num == ev.joy, self.joys)[0]
                j.hat(ev.hat*4, ev.value[0] == -1)
                j.hat(ev.hat*4+1, ev.value[0] == 1)
                j.hat(ev.hat*4+2, ev.value[1] == 1)
                j.hat(ev.hat*4+3, ev.value[1] == -1)
            elif ev.type == pygame.JOYBUTTONUP:
                j = filter(lambda j: j.num == ev.joy, self.joys)[0]
                j.btn(ev.button, False)
            elif ev.type == pygame.JOYBUTTONDOWN:
                j = filter(lambda j: j.num == ev.joy, self.joys)[0]
                j.btn(ev.button, True)
        
        self.mode.logic(t)
    
    def render(self):
        self.mode.render()
    
    def draw(self):
        self.screen.render()
        pygame.display.flip()

def main():
    return Engine()()

if __name__=='__main__':
    sys.exit(main())

