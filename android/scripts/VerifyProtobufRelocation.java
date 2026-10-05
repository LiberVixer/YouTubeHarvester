import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.commons.ClassRemapper;
import org.objectweb.asm.commons.Remapper;
import org.objectweb.asm.util.TraceClassVisitor;

/** Compare all class instructions and metadata, independently of constant-pool order. */
public final class VerifyProtobufRelocation {
    private static final String FROM = "com/google/protobuf/";
    private static final String TO = "androidx/datastore/preferences/protobuf/";
    private static final Remapper RELOCATION = new Remapper(Opcodes.ASM9) {
        @Override public String map(String name) {
            return name.startsWith(FROM) ? TO + name.substring(FROM.length()) : name;
        }

        @Override public Object mapValue(Object value) {
            if (value instanceof String) {
                String text = (String) value;
                if (text.startsWith(FROM)) return map(text);
                String dotted = FROM.replace('/', '.');
                if (text.startsWith(dotted)) {
                    return TO.replace('/', '.') + text.substring(dotted.length());
                }
            }
            return super.mapValue(value);
        }
    };

    private static String trace(byte[] data, boolean relocate) {
        StringWriter output = new StringWriter();
        ClassVisitor visitor = new TraceClassVisitor(new PrintWriter(output));
        if (relocate) visitor = new ClassRemapper(visitor, RELOCATION);
        new ClassReader(data).accept(visitor, 0);
        return output.toString();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException("original.jar relocated.jar");
        int classes = 0;
        int identicalBytes = 0;
        Set<String> expected = new HashSet<>();
        try (ZipFile original = new ZipFile(Path.of(args[0]).toFile());
             ZipFile relocated = new ZipFile(Path.of(args[1]).toFile())) {
            for (ZipEntry entry : original.stream().filter(e -> e.getName().endsWith(".class")).toList()) {
                if (!entry.getName().startsWith(FROM)) {
                    throw new IllegalStateException("Unexpected original class: " + entry.getName());
                }
                String name = TO + entry.getName().substring(FROM.length());
                if (!expected.add(name)) throw new IllegalStateException("Duplicate class: " + name);
                ZipEntry target = relocated.getEntry(name);
                if (target == null) throw new IllegalStateException("Missing relocated class: " + name);
                byte[] source = original.getInputStream(entry).readAllBytes();
                byte[] binary = relocated.getInputStream(target).readAllBytes();
                if (!trace(source, true).equals(trace(binary, false))) {
                    throw new IllegalStateException("Relocation bytecode/metadata mismatch: " + name);
                }
                ClassWriter writer = new ClassWriter(0);
                new ClassReader(source).accept(new ClassRemapper(writer, RELOCATION), 0);
                if (Arrays.equals(writer.toByteArray(), binary)) identicalBytes++;
                classes++;
            }
            Set<String> actual = new HashSet<>();
            for (ZipEntry entry : relocated.stream().filter(e -> e.getName().endsWith(".class")).toList()) {
                if (!actual.add(entry.getName())) throw new IllegalStateException("Duplicate relocated class");
            }
            if (classes == 0 || !actual.equals(expected)) {
                throw new IllegalStateException("Relocated class inventory mismatch");
            }
        }
        System.out.printf("{\"classCount\":%d,\"bytecodeAndMetadataMatches\":%d,"
                + "\"exactRemappedClassBytes\":%d,\"jarReproducibilityVerified\":false}%n",
                classes, classes, identicalBytes);
    }
}
