package {{APPLICATION_ID}}.bridge

/**
 * A bounded record of everything that went wrong inside the page.
 *
 * A WebView fails silently by design. A module script that 404s, a stylesheet that never
 * arrives, an uncaught TypeError during hydration -- none of them crash the app, none of
 * them fail a Gradle task, and none of them reach logcat unless something asks. What the
 * user gets is a blank screen and no signal, which is how a wrong asset mount survived
 * twenty-one preflight checks, a unit suite and an instrumented test simultaneously.
 *
 * So the shell records them and serves them at GET /__sag/diagnostics, and
 * GET /__sag/health carries the failure count so a test can assert zero.
 *
 * No Android imports here on purpose: the bounding and ordering is the part worth
 * testing, and PageLogTest exercises it as an ordinary JVM unit test -- the same split
 * PendingReplies uses, for the same reason.
 */
class PageLog(private val capacity: Int = DEFAULT_CAPACITY) {

    /** `isFailure` is what /__sag/health counts; console noise is kept but not counted. */
    enum class Kind(val wire: String, val isFailure: Boolean) {
        LOG("log", false),
        WARN("warn", false),
        ERROR("error", true),
        RESOURCE("resource", true),
        HTTP("http", true),
    }

    /** [seq] is assigned by [add]; whatever a caller passes is overwritten. It is the
     * cursor for `GET /__sag/diagnostics?since=N`, so a harness polling a long-lived page
     * reads only what is new instead of re-reading -- and re-judging -- the whole buffer. */
    data class Entry(
        val kind: Kind,
        val message: String,
        val source: String? = null,
        val line: Int? = null,
        val seq: Long = 0,
    )

    private val entries = ArrayDeque<Entry>()
    private var nextSeq = 1L

    /** Oldest entries are dropped first: the first error is usually the cause, but an
     * unbounded buffer on a page that errors in a render loop is a memory leak. */
    @Synchronized
    fun add(entry: Entry) {
        while (entries.size >= capacity) entries.removeFirst()
        entries.addLast(entry.copy(seq = nextSeq++))
    }

    /** Entries with seq > [since]. Sequence numbers keep rising across [clear] and
     * eviction, so a cursor never matches a different entry than the one it was taken at. */
    @Synchronized
    fun snapshot(since: Long = 0): List<Entry> = entries.filter { it.seq > since }

    @Synchronized
    fun failures(since: Long = 0): List<Entry> = entries.filter { it.kind.isFailure && it.seq > since }

    @Synchronized
    fun clear() = entries.clear()

    companion object {
        const val DEFAULT_CAPACITY = 200
    }
}
