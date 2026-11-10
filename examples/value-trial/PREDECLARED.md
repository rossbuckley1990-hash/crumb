# Independent value trial, declared before the runs

This is a constructed but ordinary order-import maintenance task, not a real
customer case or upstream bug. Two identical workspaces receive the same task,
source, and 6,002-record CSV. Both agents can inspect every source/data byte.
One arm additionally has Crumb available and is told its invocation. The other
has ordinary shell/Python. No source or data is hidden from either arm.

The task requires a compact reproducer, explanation, repair, a regression
check, and successful processing of the original full input. The policy is
explicit in task.txt. The independent oracle lives outside both workspaces;
it checks the policy on separately constructed inputs and the full CSV.

Record wall-clock time from dispatch to final answer, number of tool calls if
visible, correctness, original-input SHA-256 preservation, reproducer row count,
and whether the agent authored a reduction script. The five-minute budget is
equal. A passing test suite or a smaller file is not by itself product-value
proof. If both agents finish correctly without a material time/effort difference,
report that null result. One task with two agents is exploratory evidence only.

Predetermined correctness gates:
1. Full original input succeeds and totals equal an independent Decimal-based
   reference keyed by supplier/order reference/line number.
2. Repeated identical lines within the same key count once.
3. Distinct suppliers with equal order reference/line number remain separate.
4. Conflicting rows within the same full key still fail.
5. Original full CSV hash matches its recorded value.
6. The supplied compact reproducer fails under the original importer and
   succeeds under the repaired importer, while retaining its CSV header.

No adoption, market-success or general agent-productivity claims can follow
from this trial. The design intentionally permits a strong agent to spot the
source defect directly without Crumb; we are not withholding that route.
