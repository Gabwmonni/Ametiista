# A Ametista em 3D: como editar

O rosto da Ametista (na barra do PC e no app do celular) é uma **malha 3D** feita no Blender, desenhada pelo app em
estilo anime (luz e sombra chapadas, contorno, olhos e boca "desenhados" por cima). Tudo nela é editável e animável.

| Arquivo | O que é |
|---|---|
| `modelo/ametista.blend` | **O arquivo para editar** no Blender (4.2 ou mais novo; feito no 5.0) |
| `modelo/construir_ametista.py` | O script que construiu o modelo do zero (proporções, olhos, cabelo, joias, expressões) |
| `modelo/compactar_glb.py` | Deixa o `.glb` exportado leve para o app (16 bits), sem mudar a aparência |
| `modelo/aplicar_modelo.bat` | Depois de exportar: compacta e coloca no app (PC e celular) |
| `web/ametista.glb` | O que o app usa (a mesma coisa em `celular/public/ametista.glb`) |

## Editar no Blender (o caminho mais comum)

1. Abra `modelo/ametista.blend` no Blender.
2. Mude o que quiser: formas, cores dos materiais, o cabelo, as joias, as expressões (shape keys).
3. **Arquivo → Exportar → glTF 2.0 (.glb/.gltf)** com:
   - Formato: **glTF Binary (.glb)**;
   - Incluir: marque **Propriedades personalizadas** (Custom Properties), que guardam as cores de sombra e de contorno;
   - Malha: **Shape Keys** ligado; "Shape Key Normals" pode ficar desligado;
   - salve como **`modelo\exportado.glb`**.
4. Dê dois cliques em **`modelo\aplicar_modelo.bat`** e reabra a Ametista. Para o celular: `publicar_celular.bat`.

> Guarde o seu `.blend`: ao instalar uma versão nova da Ametista, o `web\ametista.glb` volta para o original.
> É só repetir os passos 3 e 4.

## O que o app precisa encontrar (os nomes são o "contrato")

**O pescoço:** o objeto vazio **`Cabeca`**. Tudo o que é da cabeça é filho dele; o app gira a cabeça em volta dele
(acenar, negar, inclinar, olhar em volta, respirar). O que não é filho (pescoço e roupa) fica parado.

**Os materiais**, pelo nome (a cor vem da Base Color do material; os extras `sombra` e `contorno` são cores `#rrggbb`):

| Nome | Como o app pinta |
|---|---|
| `pele`, `cabelo`, `roupa`, `roupa_detalhe`, `metal`, `cristal` | Anime: luz e sombra chapadas e contorno. O cabelo ganha o "anel" de brilho e balança; metal e cristal brilham iridescentes |
| `vidro` | Transparente e iridescente (o monóculo) |
| `olho_branco` | O branco do olho, e também a **máscara**: íris, pupila e brilhos só aparecem dentro dele |
| `iris`, `iris_estrela`, `pupila`, `brilho_olho` | Desenhados dentro do branco do olho (a íris usa as cores dos vértices, o degradê) |
| `cilios`, `cilios_baixo`, `vinco`, `sombra_olho`, `sobrancelha` | Desenhados por cima do rosto (a sobrancelha aparece até por cima da franja) |
| `boca_dentro` | O escuro da boca, e a **máscara** dos `dentes` e da `lingua` |
| `linha_boca`, `labio`, `nariz`, `blush`, `pele_sombra` | Desenhados por cima do rosto (o blush aparece quando ela está feliz) |

Um material novo pode usar um desses nomes com um final, por exemplo `cabelo_mechas` ou `metal_ouro`.

**As expressões** (shape keys; o app mistura várias ao mesmo tempo):

| Shape key | Quando |
|---|---|
| `piscar_direito`, `piscar_esquerdo` | Piscar, dormir, modo privado |
| `olhos_felizes` | Olhos "^^" quando ela está feliz |
| `arregalar` | Surpresa, alerta, ouvindo com atenção |
| `olhar_esquerda`, `olhar_direita`, `olhar_cima`, `olhar_baixo` | Para onde ela olha (na tela) |
| `boca_a`, `boca_e`, `boca_i`, `boca_o`, `boca_u` | Falando, com o volume da voz |
| `sorriso`, `triste`, `bravo` | A boca das emoções (sorriso junto com `boca_a` = sorriso aberto) |
| `sobrancelhas_cima`, `sobrancelhas_bravas`, `sobrancelhas_tristes`, `sobrancelha_pensativa` | As sobrancelhas das emoções |

Faltou alguma? O app simplesmente não usa aquela expressão; o resto funciona.

## Reconstruir do zero pelo script

Para mudar proporções gerais (tamanho dos olhos, largura do rosto, número de mechas...), o jeito mais limpo é o script:

```
blender --background --python modelo/construir_ametista.py
```

(ou `python modelo/construir_ametista.py` com o módulo do Blender: `pip install bpy`). Ele recria o `.blend`, o
`web/ametista.glb` e a cópia do celular. As medidas ficam no começo de cada parte: `PERFIL` (o formato do rosto),
`OLHO_X/OLHO_Z/OLHO_W/OLHO_H` (os olhos), `BOCA_Z` (a boca), as listas de mechas em `cabelo()`.

## Leveza

~20 mil triângulos, sem texturas (só cores): o modelo do app tem ~360 KB (~180 KB para baixar no celular, uma vez só,
depois fica guardado). A cada quadro só as partes que mexem (olhos, boca, sobrancelhas) são recalculadas, e só quando
mudam. Sem WebGL, o app usa o rosto de reserva (a ilustração animada, `rosto2d.js`).
