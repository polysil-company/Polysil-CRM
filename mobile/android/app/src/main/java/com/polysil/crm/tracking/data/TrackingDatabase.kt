package com.polysil.crm.tracking.data

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import com.polysil.crm.tracking.core.PointStore
import com.polysil.crm.tracking.core.TrackPoint

/** TRK-008 · Every fix stays here until the server counts or names it. */
@Database(entities = [PointEntity::class], version = 1, exportSchema = false)
abstract class TrackingDatabase : RoomDatabase() {
    abstract fun points(): PointDao

    companion object {
        @Volatile private var instance: TrackingDatabase? = null

        fun get(context: Context): TrackingDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    TrackingDatabase::class.java,
                    "polysil-tracking.db",
                ).build().also { instance = it }
            }
    }
}

/** The core's [PointStore] on Room. Called off the main thread only. */
internal class RoomPointStore(private val dao: PointDao) : PointStore {
    fun add(point: TrackPoint) = dao.insert(PointEntity.of(point))

    override fun oldest(limit: Int): List<TrackPoint> = dao.oldest(limit).map { it.toPoint() }

    override fun delete(ids: Collection<String>) {
        // SQLite caps the variables in one statement; delete in slices.
        ids.chunked(SQL_SLICE).forEach { dao.delete(it) }
    }

    override fun count(): Int = dao.count()

    private companion object {
        const val SQL_SLICE = 500
    }
}
