import androidx.compose.material.icons.generator.CoreIcons
import androidx.compose.material.icons.generator.IconProcessor
import androidx.compose.material.icons.generator.IconWriter
import java.io.File

fun main(args: Array<String>) {
    val generator = File(args[0])
    val output = File(args[1]).apply { mkdirs() }
    val icons = IconProcessor(
        listOf("filled", "outlined", "rounded", "twotone", "sharp").map {
            generator.resolve("raw-icons/$it")
        },
        generator.resolve("api/icons.txt"), output.resolve("icons.txt"),
        generator.resolve("api/automirrored_icons.txt"), output.resolve("automirrored_icons.txt")
    ).process()
    val writer = IconWriter(icons)
    writer.generateTo(output.resolve("core")) { it in CoreIcons }
    writer.generateTo(output.resolve("extended")) { it !in CoreIcons }
    println("Generated ${icons.size} source vectors")
}
