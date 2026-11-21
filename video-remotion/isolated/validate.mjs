import ts from 'typescript';

const words = new Set('constructor prototype __proto__ globalThis window document process require eval Function import.meta fetch XMLHttpRequest WebSocket Reflect Proxy Object Date performance localStorage sessionStorage'.split(' '));
const tags = new Set('svg g defs path circle ellipse rect line polyline polygon text tspan linearGradient radialGradient stop clipPath marker title desc div span p'.split(' '));
const hooks = new Set(['useCurrentFrame', 'useVideoConfig', 'interpolate', 'spring', 'Easing']);
const math = new Set('abs atan2 ceil cos exp floor hypot log log10 max min pow round sign sin sqrt tan trunc'.split(' '));
const methods = new Set('map filter slice join toFixed'.split(' '));
const syntax = new Set((
  'SourceFile EndOfFileToken ImportDeclaration ImportClause NamedImports ImportSpecifier ExportKeyword DefaultKeyword ' +
  'FunctionDeclaration ArrowFunction Parameter Block ReturnStatement VariableStatement VariableDeclarationList VariableDeclaration ' +
  'ObjectBindingPattern BindingElement Identifier TypeLiteral PropertySignature NumberKeyword StringKeyword BooleanKeyword ' +
  'ArrayType TypeReference ParenthesizedExpression AsExpression IfStatement ConditionalExpression ' +
  'BinaryExpression PrefixUnaryExpression PropertyAccessExpression ElementAccessExpression CallExpression ' +
  'ArrayLiteralExpression ObjectLiteralExpression PropertyAssignment ShorthandPropertyAssignment ' +
  'NumericLiteral StringLiteral NoSubstitutionTemplateLiteral TemplateExpression TemplateHead TemplateSpan TemplateMiddle TemplateTail ' +
  'TrueKeyword FalseKeyword NullKeyword EqualsGreaterThanToken JsxElement JsxSelfClosingElement JsxOpeningElement JsxClosingElement ' +
  'JsxFragment JsxOpeningFragment JsxClosingFragment JsxAttributes JsxAttribute JsxExpression JsxText ' +
  'PlusToken MinusToken AsteriskToken SlashToken PercentToken AsteriskAsteriskToken ' +
  'LessThanToken GreaterThanToken LessThanEqualsToken GreaterThanEqualsToken EqualsEqualsEqualsToken ExclamationEqualsEqualsToken ' +
  'AmpersandAmpersandToken BarBarToken QuestionQuestionToken ExclamationToken QuestionToken ColonToken'
).split(' ').map(name => ts.SyntaxKind[name]));

export function validate(file) {
  const program = ts.createProgram([file], {
    jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler, noEmit: true, strict: true,
    skipLibCheck: true, types: ['react'],
  });
  const source = program.getSourceFile(file);
  const errors = program.getSyntacticDiagnostics(source);
  const stop = (node, message) => {
    const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
    throw new Error(`line ${line}: ${message}`);
  };
  if (errors.length) throw new Error(`TypeScript syntax error TS${errors[0].code}`);
  if (source.referencedFiles.length || source.typeReferenceDirectives.length
      || source.libReferenceDirectives.length || source.commentDirectives?.length) {
    throw new Error('TypeScript directives are forbidden');
  }
  const checker = program.getTypeChecker();
  const localFunction = (name) => {
    const declaration = checker.getSymbolAtLocation(name)?.valueDeclaration;
    return declaration?.getSourceFile() === source && (
      ts.isFunctionDeclaration(declaration) ||
      (ts.isVariableDeclaration(declaration) && declaration.initializer && ts.isArrowFunction(declaration.initializer))
    );
  };
  const imported = new Set();
  for (const statement of source.statements) {
    if (ts.isFunctionDeclaration(statement) || ts.isVariableStatement(statement)) continue;
    if (!ts.isImportDeclaration(statement) || statement.moduleSpecifier.text !== 'remotion'
        || statement.importClause?.name || !statement.importClause?.namedBindings
        || !ts.isNamedImports(statement.importClause.namedBindings)) stop(statement, 'Only named imports from remotion are allowed');
    for (const entry of statement.importClause.namedBindings.elements) {
      if (entry.propertyName || !hooks.has(entry.name.text)) stop(entry, 'Unsupported Remotion API');
      imported.add(entry.name.text);
    }
  }
  const entry = source.statements.filter(s => ts.isFunctionDeclaration(s) && s.modifiers?.some(m => m.kind === ts.SyntaxKind.DefaultKeyword));
  if (entry.length !== 1 || entry[0].name?.text !== 'Visual' || entry[0].parameters.length !== 1) {
    throw new Error('Expected export default function Visual with one props parameter');
  }
  let count = 0;
  function visit(node) {
    if (++count > 9000) stop(node, 'Code is too complex');
    if (!syntax.has(node.kind)) stop(node, `Unsupported syntax ${ts.SyntaxKind[node.kind]}`);
    if (ts.isIdentifier(node) && words.has(node.text)) stop(node, 'Forbidden identifier');
    if (ts.isIdentifier(node)) {
      const symbol = checker.getSymbolAtLocation(node);
      const property = (ts.isPropertyAccessExpression(node.parent) && node.parent.name === node)
        || ts.isJsxAttribute(node.parent) || ts.isJsxOpeningLikeElement(node.parent) || ts.isJsxClosingElement(node.parent)
        || ts.isPropertyAssignment(node.parent) && node.parent.name === node;
      if (!property && !['Math', 'undefined'].includes(node.text) && symbol?.declarations?.length
          && !symbol.declarations.some(d => d.getSourceFile() === source)) stop(node, 'External global is forbidden');
    }
    if ((ts.isStringLiteralLike(node) || ts.isTemplateLiteralToken(node))
        && /(?:https?:|file:|javascript:|data:|url\(\s*[^#])/i.test(node.text)) stop(node, 'External references are forbidden');
    if (ts.isElementAccessExpression(node) && !ts.isNumericLiteral(node.argumentExpression)
        && !(ts.isIdentifier(node.argumentExpression) && checker.getTypeAtLocation(node.argumentExpression).flags & ts.TypeFlags.Number)) {
      stop(node, 'Only numeric indexing is allowed');
    }
    if (ts.isVariableDeclarationList(node) && !(node.flags & ts.NodeFlags.Const)) stop(node, 'Use const bindings');
    if (ts.isJsxOpeningLikeElement(node) || ts.isJsxClosingElement(node)) {
      const name = node.tagName;
      // A capitalized tag must resolve to a function whose body we also check.
      if (!ts.isIdentifier(name) || !(tags.has(name.text) ||
          (/^[A-Z]/.test(name.text) && localFunction(name)))) stop(node, 'Unsupported element');
    }
    if (ts.isJsxAttribute(node) && /^(on|href|src|ref$|dangerously|form|contentEditable|xmlns)/i.test(node.name.getText(source))) stop(node, 'Unsupported JSX attribute');
    if (ts.isPropertyAssignment(node) && /^(animation|transition)/i.test(node.name.getText(source).replace(/['"]/g,''))) stop(node, 'CSS time-based motion is forbidden');
    if (ts.isCallExpression(node)) {
      const call = node.expression;
      if (ts.isIdentifier(call)) {
        if (!imported.has(call.text) && !localFunction(call)) stop(node, 'Unsupported function call');
      } else if (ts.isPropertyAccessExpression(call)) {
        const owner = call.expression.getText(source);
        const easing = owner === 'Easing' && imported.has(owner) && ['bezier','in','out','inOut','poly'].includes(call.name.text);
        if (!(owner === 'Math' && math.has(call.name.text)) && !easing && !methods.has(call.name.text)) stop(node, 'Unsupported method call');
      } else stop(node, 'Unsupported call target');
    }
    ts.forEachChild(node, visit);
  }
  visit(source);
  const semantic = program.getSemanticDiagnostics(source);
  if (semantic.length) {
    const line = source.getLineAndCharacterOfPosition(semantic[0].start ?? 0).line + 1;
    throw new Error(`line ${line}: TypeScript type error TS${semantic[0].code}`);
  }
}
