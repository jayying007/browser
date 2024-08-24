# Browser

Browser分为Chrome和Tabs。

Browser有几个关键阶段：
- composite：display_list中找到所有的non_composited_commands，并生成对应的CompositedLayer
- raster：获取所有displayItem，并绘制到Canvas上。每个CompositedLayer都对应一个Canvas
- draw：把这些CompositedLayer和Chrome的surface，绘制到Browser的canvas上

# Tab

每个Tab有一个TaskRunner来做任务调度。由于有iframe，所以每个Tab又有一颗frame树。

加载url后，经过html解析、layout计算，得到绘制命令display_list，通过commit提交给Browser