# A Ametista em 3D: como editar

A Ametista da barra do PC e do app do celular é o **modelo 3D dela** (o busto: rosto, cabelo, joias, monóculo e
roupa), montado no Blender com um esqueleto e uma "máscara" animada no rosto. Parada, ela é igual ao modelo; com
as expressões, ela pisca, olha em volta, fala mexendo a boca, sorri, fica triste, brava ou surpresa, e vira a
cabeça de verdade, em 3D.

| Arquivo | O que é |
|---|---|
| `modelo/ametista.blend` | **O arquivo para editar** no Blender (4.2 ou mais novo; feito no 5.0) |
| `modelo/fonte/ametista_3d.glb` | O modelo 3D original dela (a malha inteira e a cor em 4096 × 4096) |
| `modelo/fonte/cor_corpo.webp` | A cor do corpo já reduzida para o app (1024 × 1024; o `.blend` usa esta) |
| `modelo/rosto/frente.png` | A foto de frente do rosto, tirada do próprio modelo (`renderizar_rosto.py`) |
| `modelo/rosto/marcas.json` | As marcações do rosto nessa foto: olhos, íris, cílios, boca, sobrancelhas, contorno |
| `modelo/rosto/atlas.png` | A textura da máscara: a pele, o branco dos olhos, as íris, os cílios e a boca por dentro |
| `modelo/renderizar_rosto.py` | Tira a foto de frente do rosto |
| `modelo/preparar_rosto.py` | Monta o atlas a partir da foto e das marcações |
| `modelo/construir_ametista.py` | Monta a Ametista animável no Blender e exporta para o app |
| `modelo/compactar_glb.py` | Deixa o `.glb` exportado leve para o app, sem mudar a aparência |
| `modelo/aplicar_modelo.bat` | Depois de exportar à mão: compacta e coloca no app (PC e celular) |
| `web/ametista.glb` | O que o app usa (a mesma coisa em `celular/public/ametista.glb`) |

## As peças

| Objeto | O que é |
|---|---|
| `Corpo` | O modelo 3D dela, com menos triângulos (o rosto guarda mais detalhe), com a cor dele |
| `Rosto` | A **máscara**: colada na superfície do rosto, com buracos nos olhos e na boca; a borda some aos poucos e se funde com o `Corpo` |
| `Olho_D`, `Olho_E` | O branco de cada olho, atrás das pálpebras |
| `Iris_D`, `Iris_E` | As íris (mexem para olhar) |
| `Cilios_D`, `Cilios_E` | Os cílios de cima (giram para baixo junto com a pálpebra quando ela pisca) |
| `Boca_dentro` | Os dentes de cima, o escuro e a língua (aparecem quando ela abre a boca) |
| `Blush` | O rubor (quando ela está feliz) |
| `Brilhos` | Os pontinhos onde o app acende o brilho de cristal |
| `Esqueleto` | Os ossos `raiz`, `peito` (respira), `pescoco` e `cabeca` (acenar, negar, inclinar, olhar em volta) |

## Editar no Blender

1. Abra `modelo/ametista.blend` no Blender.
2. Mude o que quiser: as cores (a textura `cor_corpo.webp` e o `atlas.png`), as expressões (shape keys da
   `Rosto`, das íris, dos cílios e da boca), os pesos dos ossos.
3. **Arquivo → Exportar → glTF 2.0 (.glb/.gltf)** com:
   - Formato: **glTF Binary (.glb)**;
   - Incluir: marque **Propriedades personalizadas** (Custom Properties), que guardam o enquadramento;
   - Dados → Malha: **Shape Keys** ligado; Dados → Armature/Skinning ligado;
   - Material → Imagens: **WebP**;
   - salve como **`modelo\exportado.glb`**.
4. Dê dois cliques em **`modelo\aplicar_modelo.bat`** e reabra a Ametista. Para o celular: `publicar_celular.bat`.

> Guarde o seu `.blend`: ao instalar uma versão nova da Ametista, o `web\ametista.glb` volta para o original.
> É só repetir os passos 3 e 4.

## O que o app precisa encontrar (os nomes são o "contrato")

**Os ossos:** `raiz`, `peito`, `pescoco` e `cabeca`, em pé (sem giro de repouso). O app gira a cabeça em volta do
pivô dela e do pescoço, e o peito sobe e desce na respiração.

**Os materiais**, pelo nome (um material novo pode usar um desses nomes com um final, por exemplo `cilios_baixo`):

| Nome | Como o app pinta |
|---|---|
| `corpo`, `olho`, `boca_dentro` | A cor da textura, sem luz (a luz já está pintada no modelo) |
| `rosto` | A máscara: a borda com transparência se funde com o que está atrás |
| `iris`, `cilios` | Camadas com transparência, por cima |
| `blush` | O rubor, que aparece aos poucos quando ela está feliz |
| `brilho` | Não é desenhado: marca onde o app acende os brilhos de cristal |

**As expressões** (shape keys; o app mistura várias ao mesmo tempo):

| Shape key | Quando |
|---|---|
| `piscar_direito`, `piscar_esquerdo` | Piscar, dormir, modo privado |
| `olhos_felizes` | Olhos sorrindo quando ela está feliz |
| `arregalar` | Surpresa, alerta, ouvindo com atenção |
| `olhar_esquerda`, `olhar_direita`, `olhar_cima`, `olhar_baixo` | Para onde ela olha |
| `boca_a`, `boca_e`, `boca_i`, `boca_o`, `boca_u` | Falando, com o volume da voz |
| `sorriso`, `triste`, `bravo` | A boca das emoções (sorriso junto com `boca_a` = sorriso aberto) |
| `sobrancelhas_cima`, `sobrancelhas_bravas`, `sobrancelhas_tristes`, `sobrancelha_pensativa` | As sobrancelhas das emoções |

Faltou alguma? O app simplesmente não usa aquela expressão; o resto funciona.

## Reconstruir do zero pelos scripts

Com o Blender como módulo do Python (`pip install bpy numpy`; para o atlas também `opencv-python-headless pillow`):

```
python modelo/renderizar_rosto.py     (só se o modelo 3D da fonte mudou: tira a foto de frente de novo)
python modelo/preparar_rosto.py       (só se a foto ou as marcações mudaram: refaz o atlas)
python modelo/construir_ametista.py   (monta tudo: o .blend, o web/ametista.glb e a cópia do celular)
```

(ou `blender --background --python modelo/construir_ametista.py`). Trocar o modelo 3D dela por outro: coloque o
`.glb` novo em `modelo/fonte/ametista_3d.glb`, tire a foto de frente e refaça as marcações do `marcas.json` nessa foto
(em pixels: os cantos e as curvas das pálpebras, o centro e o raio das íris, a boca, as sobrancelhas e o contorno do
rosto). As medidas do resto ficam no começo do `construir_ametista.py`: `REDUZIR` (quanto do modelo fica),
`AFASTA` (a distância de cada camada até a pele), `PIVOS` (onde ficam os ossos).

## Leveza

~27 mil triângulos e duas texturas WebP (a cor do corpo e o atlas do rosto): o modelo do app tem ~1,1 MB (~700 KB
para baixar no celular, uma vez só; depois fica guardado). As texturas são lidas uma vez só, e a cada quadro só as
peças que mexem (pálpebras, íris, boca, sobrancelhas) são recalculadas, e só quando mudam. Sem WebGL, o app usa o
rosto de reserva (a ilustração animada, `rosto2d.js`).
