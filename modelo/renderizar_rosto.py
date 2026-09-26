"""Fotografa o rosto da Ametista de frente (só a cor, sem luz), direto do modelo 3D.

O rosto animado é uma "máscara" em cima do modelo 3D: uma malha colada na superfície do rosto, com a cor desta
foto. Parada, ela é igual ao modelo; mexendo, as pálpebras descem, a boca abre, as sobrancelhas sobem.
O preparar_rosto.py usa esta foto (e as marcações em rosto/marcas.json) para separar os cílios, montar o branco
dos olhos, a íris inteira e a boca por dentro.

Uso (com o módulo do Blender):  python modelo/renderizar_rosto.py
Gera modelo/rosto/frente.png e modelo/rosto/frente.json (a janela: que pedaço do modelo cada pixel mostra).
"""
import json
import math
import os

import bpy

AQUI = os.path.dirname(os.path.abspath(__file__))
FONTE = os.path.join(AQUI, "fonte", "ametista_3d.glb")
PASTA = os.path.join(AQUI, "rosto")
# a janela da foto, em unidades do modelo (Blender: x para a direita dela... da tela; z para cima)
CENTRO_X, CENTRO_Z, LADO = 0.0, 0.70, 0.30
PIXELS = 720


def fotografar():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=FONTE)
    ob = next(o for o in bpy.context.scene.objects if o.type == "MESH")
    nt = ob.active_material.node_tree
    tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
    saida = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    for n in list(nt.nodes):
        if n not in (tex, saida):
            nt.nodes.remove(n)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], saida.inputs["Surface"])
    cena = bpy.context.scene
    cena.render.engine = "CYCLES"
    cena.cycles.samples = 16
    cena.cycles.device = "CPU"
    cena.cycles.seed = 1
    cena.render.filter_size = 1.0
    cena.view_settings.view_transform = "Standard"
    cena.render.film_transparent = True
    cena.render.resolution_x = cena.render.resolution_y = PIXELS
    cam = bpy.data.objects.new("foto", bpy.data.cameras.new("foto"))
    cena.collection.objects.link(cam)
    cena.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = LADO
    cam.location = (CENTRO_X, -3, CENTRO_Z)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    os.makedirs(PASTA, exist_ok=True)
    cena.render.filepath = os.path.join(PASTA, "frente.png")
    bpy.ops.render.render(write_still=True)
    janela = {"x0": CENTRO_X - LADO / 2, "x1": CENTRO_X + LADO / 2, "z0": CENTRO_Z - LADO / 2,
              "z1": CENTRO_Z + LADO / 2, "pixels": PIXELS}
    with open(os.path.join(PASTA, "frente.json"), "w", encoding="utf-8") as f:
        json.dump(janela, f, indent=1)
    return janela


if __name__ == "__main__":
    print(fotografar())
