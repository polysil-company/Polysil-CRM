/**
 * Project-specific lint rules that keep AI-written and human-written code
 * honest about the conventions in AGENTS.md.
 *
 * - local/logger-file-matches     createLogger({ file }) must equal the real path under src/
 * - local/test-describe-data-id   top-level describe() titles start with a Data ID: "[LEAD-001] …"
 */

const DATA_ID_TITLE = /^\[[A-Z]{2,6}-\d{3}\] \S/;

/** @param {string} filename */
function pathUnderSrc(filename) {
  const normalized = filename.replaceAll("\\", "/");
  const marker = "/src/";
  const index = normalized.lastIndexOf(marker);
  return index === -1 ? null : normalized.slice(index + marker.length);
}

/** @type {import("eslint").Rule.RuleModule} */
const loggerFileMatches = {
  meta: {
    type: "problem",
    fixable: "code",
    docs: { description: "createLogger({ file }) must match the file path relative to src/." },
    messages: {
      missing:
        'createLogger needs a string literal `file` equal to this file\'s path under src/ ("{{expected}}").',
      mismatch: 'Logger `file` is "{{actual}}" but this file is "{{expected}}".',
    },
    schema: [],
  },
  create(context) {
    const expected = pathUnderSrc(context.filename);
    // The logger's own implementation re-scopes loggers internally.
    if (expected === null || expected.startsWith("lib/logger/")) {
      return {};
    }

    return {
      CallExpression(node) {
        if (node.callee.type !== "Identifier" || node.callee.name !== "createLogger") {
          return;
        }
        const [options] = node.arguments;
        if (!options || options.type !== "ObjectExpression") {
          context.report({ node, messageId: "missing", data: { expected } });
          return;
        }
        const fileProperty = options.properties.find(
          (property) =>
            property.type === "Property" &&
            property.key.type === "Identifier" &&
            property.key.name === "file",
        );
        if (
          !fileProperty ||
          fileProperty.type !== "Property" ||
          fileProperty.value.type !== "Literal" ||
          typeof fileProperty.value.value !== "string"
        ) {
          context.report({ node: options, messageId: "missing", data: { expected } });
          return;
        }
        const literal = fileProperty.value;
        if (literal.value !== expected) {
          context.report({
            node: literal,
            messageId: "mismatch",
            data: { actual: String(literal.value), expected },
            fix: (fixer) => fixer.replaceText(literal, JSON.stringify(expected)),
          });
        }
      },
    };
  },
};

/** @type {import("eslint").Rule.RuleModule} */
const testDescribeDataId = {
  meta: {
    type: "suggestion",
    docs: { description: "Top-level describe() titles must start with a Data ID." },
    messages: {
      missing:
        'Start the top-level describe title with the Data ID it covers, e.g. describe("[LEAD-001] leads list"). See Docs/Data-IDs.md.',
    },
    schema: [],
  },
  create(context) {
    return {
      "Program > ExpressionStatement > CallExpression[callee.name='describe']"(node) {
        const [title] = node.arguments;
        const valid =
          title !== undefined &&
          title.type === "Literal" &&
          typeof title.value === "string" &&
          DATA_ID_TITLE.test(title.value);
        if (!valid) {
          context.report({ node, messageId: "missing" });
        }
      },
    };
  },
};

const plugin = {
  meta: { name: "local" },
  rules: {
    "logger-file-matches": loggerFileMatches,
    "test-describe-data-id": testDescribeDataId,
  },
};

export default plugin;
